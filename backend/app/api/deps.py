"""Request dependencies: DB session, current user, workspace RBAC, rate limits."""
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Optional

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.responses import AppError, forbidden, not_found
from app.core.security import SESSION_COOKIE, decode_access_token
from app.db import get_db
from app.models.orm import Innovation, User, UserRole, WorkspaceMember, WorkspaceRole

__all__ = ["get_db", "current_user", "require_admin", "WorkspaceCtx", "workspace_ctx", "innovation_ctx", "rate_limit"]

ROLE_RANK = {
    WorkspaceRole.VIEWER: 0,
    WorkspaceRole.REVIEWER: 1,
    WorkspaceRole.RESEARCHER: 2,
    WorkspaceRole.ADMIN: 3,
    WorkspaceRole.OWNER: 4,
}


def _token_from_request(request: Request, authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
) -> User:
    token = _token_from_request(request, authorization)
    if not token:
        raise AppError(401, "UNAUTHORIZED", "Please sign in to continue.")
    user_id = decode_access_token(token)
    if not user_id:
        raise AppError(401, "SESSION_EXPIRED", "Your session has expired. Please sign in again.")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "This account is not active.")
    # CSRF defence for cookie-authenticated writes: browsers cannot set this
    # custom header cross-site without a CORS preflight we do not allow.
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and not authorization
        and request.headers.get("x-requested-with") != "ipsakti"
    ):
        raise AppError(403, "CSRF_CHECK_FAILED", "Request is missing the X-Requested-With header.")
    request.state.user_id = user.id
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise forbidden("Administrator access is required.")
    return user


@dataclass
class WorkspaceCtx:
    user: User
    workspace_id: str
    role: WorkspaceRole

    def require(self, minimum: WorkspaceRole) -> None:
        if self.user.role == UserRole.ADMIN:
            return
        if ROLE_RANK[self.role] < ROLE_RANK[minimum]:
            raise forbidden(f"This action requires the {minimum.value} role or higher in this workspace.")


def resolve_workspace(db: Session, user: User, workspace_id: Optional[str]) -> WorkspaceCtx:
    q = select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    if workspace_id:
        q = q.where(WorkspaceMember.workspace_id == workspace_id)
    member = db.execute(q.order_by(WorkspaceMember.created_at)).scalars().first()
    if not member:
        if workspace_id:
            raise not_found("Workspace")
        raise AppError(409, "NO_WORKSPACE", "You are not a member of any workspace yet. Create one first.")
    return WorkspaceCtx(user=user, workspace_id=member.workspace_id, role=member.role)


def workspace_ctx(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_workspace_id: Optional[str] = Header(default=None),
) -> WorkspaceCtx:
    ctx = resolve_workspace(db, user, x_workspace_id)
    request.state.workspace_id = ctx.workspace_id
    return ctx


def load_innovation(db: Session, ctx: WorkspaceCtx, innovation_id: str) -> Innovation:
    inn = db.get(Innovation, innovation_id)
    if not inn or inn.workspace_id != ctx.workspace_id:
        raise not_found("Innovation")
    return inn


# ---------------------------------------------------------------------------
# Rate limiting (in-process sliding window; swap for Redis when REDIS_URL set)
# ---------------------------------------------------------------------------

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = Lock()


def rate_limit(bucket: str) -> Callable:
    limit = {
        "chat": settings.RATE_LIMIT_CHAT,
        "search": settings.RATE_LIMIT_SEARCH,
        "ingest": settings.RATE_LIMIT_INGEST,
        "report": settings.RATE_LIMIT_REPORT,
    }[bucket]

    def _check(request: Request, user: User = Depends(current_user)) -> None:
        key = f"{bucket}:{user.id}"
        now = time.monotonic()
        with _hits_lock:
            q = _hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                retry = int(60 - (now - q[0])) + 1
                raise AppError(
                    429,
                    "RATE_LIMITED",
                    f"Too many {bucket} requests. Limit is {limit} per minute; try again in {retry}s.",
                )
            q.append(now)

    return _check


def innovation_ctx(
    innovation_id: str,
    ctx: WorkspaceCtx = Depends(workspace_ctx),
    db: Session = Depends(get_db),
) -> tuple[WorkspaceCtx, Innovation]:
    """Resolve an innovation by id across the user's workspaces (path-scoped access)."""
    inn = db.get(Innovation, innovation_id)
    if not inn:
        raise not_found("Innovation")
    if inn.workspace_id != ctx.workspace_id:
        ctx = resolve_workspace(db, ctx.user, inn.workspace_id)
    return ctx, inn
