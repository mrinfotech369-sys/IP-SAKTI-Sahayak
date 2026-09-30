from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.config import settings
from app.core.responses import AppError, ok
from app.core.security import SESSION_COOKIE, create_access_token, hash_password, password_problems, verify_password
from app.models.orm import Organization, User, Workspace, WorkspaceMember, WorkspaceRole
from app.schemas import LoginIn, RegisterIn
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


def _set_session(response: Response, token: str, expires: datetime) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", secure=settings.is_production,
        max_age=int((expires - datetime.now(timezone.utc)).total_seconds()), path="/",
    )


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
    token, exp = create_access_token(user.id)
    _set_session(response, token, exp)
    return ok({"user": user_view(db, user), "token": token, "expires_at": exp.isoformat()})


@router.post("/login", summary="Sign in with email and password")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    if not user.is_active:
        raise AppError(403, "ACCOUNT_DISABLED", "This account has been disabled. Contact an administrator.")
    user.last_login = datetime.now(timezone.utc)
    audit(db, "login", user_id=user.id, entity_type="user", entity_id=user.id, request=request, commit=False)
    db.commit()
    token, exp = create_access_token(user.id)
    _set_session(response, token, exp)
    return ok({"user": user_view(db, user), "token": token, "expires_at": exp.isoformat()})


@router.post("/logout", summary="Sign out (clears the session cookie)")
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    audit(db, "logout", user_id=user.id, entity_type="user", entity_id=user.id, request=request)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return ok({"signed_out": True})


@router.get("/session", summary="Current session, or null when signed out (never 401)")
def session(request: Request, db: Session = Depends(get_db)):
    from app.core.security import decode_access_token

    token = request.cookies.get(SESSION_COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    uid = decode_access_token(token) if token else None
    user = db.get(User, uid) if uid else None
    return ok(user_view(db, user) if user and user.is_active else None)


@router.get("/me", summary="Current user and workspace memberships")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return ok(user_view(db, user))
