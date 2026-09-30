import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.config import settings
from app.core.responses import AppError, ok
from app.core.security import (
    ADMIN_SESSION_COOKIE, SESSION_COOKIE, create_access_token, decode_access_token, hash_password, password_problems, safe_client_id,
    verify_password,
)
from app.models.orm import Organization, User, UserRole, Workspace, WorkspaceMember, WorkspaceRole
from app.schemas import LoginIn, PasswordChangeIn, ProfilePatchIn, RegisterIn
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["Auth"])


def user_view(db: Session, u: User) -> dict:
    rows = db.execute(
        select(WorkspaceMember, Workspace).join(Workspace, Workspace.id == WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == u.id)
    ).all()
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role.value,
        "preferred_language": u.preferred_language,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "workspaces": [
            {"id": w.id, "name": w.name, "role": m.role.value, "confidential_mode": w.confidential_mode} for m, w in rows
        ],
    }


def _set_session(response: Response, token: str, expires: datetime, cookie: str = SESSION_COOKIE) -> None:
    response.set_cookie(
        cookie, token, httponly=True, samesite="strict" if cookie == ADMIN_SESSION_COOKIE else "lax", secure=settings.is_production,
        max_age=int((expires - datetime.now(timezone.utc)).total_seconds()), path="/",
    )


# --- Brute-force protection: sliding window per (client, email) ---------------------------------
_attempts: dict[str, deque] = defaultdict(deque)
_attempts_lock = Lock()


def _throttle_login(request: Request, email: str) -> None:
    key = f"{safe_client_id(request.client.host if request.client else None)}:{email.lower()}"
    now = time.monotonic()
    with _attempts_lock:
        q = _attempts[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.LOGIN_ATTEMPTS_PER_MINUTE:
            raise AppError(429, "TOO_MANY_LOGIN_ATTEMPTS", "Too many sign-in attempts. Wait a minute and try again.")
        q.append(now)


def _authenticate(db: Session, request: Request, body: LoginIn, event: str) -> User:
    _throttle_login(request, body.email)
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, f"{event}_failed", user_id=user.id if user else None, entity_type="auth", request=request,
              email=body.email.lower(), reason="invalid_credentials")
        raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    if not user.is_active:
        audit(db, f"{event}_failed", user_id=user.id, entity_type="auth", request=request, reason="account_disabled")
        raise AppError(403, "ACCOUNT_DISABLED", "This account has been disabled. Contact an administrator.")
    return user


@router.post("/register", summary="Create an account (and a personal workspace)")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    problems = password_problems(body.password)
    if problems:
        raise AppError(422, "WEAK_PASSWORD", "Password must contain " + ", ".join(problems) + ".")
    if db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none():
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Sign in instead.")
    user = User(name=body.name.strip(), email=body.email.lower(), password_hash=hash_password(body.password), last_login=datetime.now(timezone.utc))
    org = Organization(name=body.organization or f"{body.name.split()[0]}'s organisation")
    db.add_all([user, org])
    db.flush()
    ws = Workspace(organization_id=org.id, name=body.workspace or "My Research Workspace")
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER))
    audit(db, "user_registered", user_id=user.id, workspace_id=ws.id, entity_type="user", entity_id=user.id, request=request, commit=False)
    db.commit()
    token, exp = create_access_token(user.id, scope="user")
    _set_session(response, token, exp)
    return ok({"user": user_view(db, user), "token": token, "expires_at": exp.isoformat()})


@router.post("/login", summary="Sign in to the application (user area)")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = _authenticate(db, request, body, "login")
    user.last_login = datetime.now(timezone.utc)
    audit(db, "login", user_id=user.id, entity_type="user", entity_id=user.id, request=request, commit=False)
    db.commit()
    token, exp = create_access_token(user.id, scope="user")
    _set_session(response, token, exp)
    return ok({"user": user_view(db, user), "token": token, "expires_at": exp.isoformat()})


@router.post("/logout", summary="Sign out (clears the session cookie)")
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    audit(db, "logout", user_id=user.id, entity_type="user", entity_id=user.id, request=request)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return ok({"signed_out": True})


@router.get("/session", summary="Current session, or null when signed out (never 401)")
def session(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    uid = decode_access_token(token, scope="user") if token else None
    user = db.get(User, uid) if uid else None
    return ok(user_view(db, user) if user and user.is_active else None)


@router.get("/me", summary="Current user and workspace memberships")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return ok(user_view(db, user))


@router.patch("/me", summary="Update own profile")
def update_me(body: ProfilePatchIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(user, k, v.strip() if isinstance(v, str) else v)
    audit(db, "profile_updated", user_id=user.id, entity_type="user", entity_id=user.id, request=request, fields=sorted(changes))
    return ok(user_view(db, user))


@router.post("/change-password", summary="Change own password")
def change_password(body: PasswordChangeIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(body.current_password, user.password_hash):
        audit(db, "password_change_failed", user_id=user.id, entity_type="user", entity_id=user.id, request=request)
        raise AppError(401, "INVALID_CREDENTIALS", "Current password is incorrect.")
    problems = password_problems(body.new_password)
    if problems:
        raise AppError(422, "WEAK_PASSWORD", "Password must contain " + ", ".join(problems) + ".")
    user.password_hash = hash_password(body.new_password)
    audit(db, "password_changed", user_id=user.id, entity_type="user", entity_id=user.id, request=request)
    return ok({"changed": True})


# ---------------------------------------------------------------------------
# Admin console authentication — same user table & password hashing,
# separate login, separate (shorter, SameSite=Strict) admin-scoped session.
# ---------------------------------------------------------------------------

def admin_view(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role.value,
            "last_login": u.last_login.isoformat() if u.last_login else None}


@router.post("/admin/login", summary="Sign in to the admin console (role=ADMIN only)")
def admin_login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = _authenticate(db, request, body, "admin_login")
    if user.role != UserRole.ADMIN:
        audit(db, "admin_login_denied", user_id=user.id, entity_type="auth", request=request, reason="not_admin")
        raise AppError(403, "ADMIN_ACCESS_DENIED", "This account does not have administrator access.")
    user.last_login = datetime.now(timezone.utc)
    audit(db, "admin_login", user_id=user.id, entity_type="user", entity_id=user.id, request=request, commit=False)
    db.commit()
    token, exp = create_access_token(user.id, scope="admin")
    _set_session(response, token, exp, ADMIN_SESSION_COOKIE)
    return ok({"admin": admin_view(user), "token": token, "expires_at": exp.isoformat()})


@router.post("/admin/logout", summary="Sign out of the admin console")
def admin_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    uid = decode_access_token(token, scope="admin") if token else None
    if uid:
        audit(db, "admin_logout", user_id=uid, entity_type="user", entity_id=uid, request=request)
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return ok({"signed_out": True})


@router.get("/admin/session", summary="Admin console session state (never 401)")
def admin_session(request: Request, db: Session = Depends(get_db)):
    # API (Bearer) clients present one token, checked against both scopes; browser clients carry two
    # distinct cookies. Either way, an admin-scoped credential is required for the "admin" state.
    auth = request.headers.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    admin_token = bearer or request.cookies.get(ADMIN_SESSION_COOKIE)
    uid = decode_access_token(admin_token, scope="admin") if admin_token else None
    admin = db.get(User, uid) if uid else None
    if admin and admin.is_active and admin.role == UserRole.ADMIN:
        return ok({"state": "admin", "admin": admin_view(admin)})
    # Tell the console whether a normal (non-admin) app session exists, so it can show "Access denied".
    user_token = bearer or request.cookies.get(SESSION_COOKIE)
    uuid_ = decode_access_token(user_token, scope="user") if user_token else None
    u = db.get(User, uuid_) if uuid_ else None
    if u and u.is_active:
        return ok({"state": "user_not_admin" if u.role != UserRole.ADMIN else "admin_login_required", "user": {"name": u.name, "email": u.email}})
    return ok({"state": "signed_out"})
