from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, resolve_workspace
from app.core.responses import AppError, ok
from app.models.orm import Organization, User, Workspace, WorkspaceMember, WorkspaceRole
from app.schemas import MemberIn, WorkspaceIn, WorkspacePatch
from app.services.audit import audit

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


def ws_view(w: Workspace, role: str | None = None, members: list | None = None) -> dict:
    d = {
        "id": w.id, "name": w.name, "organization_id": w.organization_id, "confidential_mode": w.confidential_mode,
        "retention_policy": w.retention_policy, "external_retrieval_allowed": w.external_retrieval_allowed,
        "created_at": w.created_at.isoformat(), "role": role,
    }
    if members is not None:
        d["members"] = members
    return d


@router.get("")
def list_workspaces(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(
        select(Workspace, WorkspaceMember.role).join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id).where(WorkspaceMember.user_id == user.id)
    ).all()
    return ok([ws_view(w, r.value) for w, r in rows])


@router.post("")
def create_workspace(body: WorkspaceIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    member = db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)).scalars().first()
    org_id = db.get(Workspace, member.workspace_id).organization_id if member else None
    if not org_id:
        org = Organization(name=f"{user.name}'s organisation")
        db.add(org)
        db.flush()
        org_id = org.id
    w = Workspace(organization_id=org_id, name=body.name, confidential_mode=body.confidential_mode, retention_policy=body.retention_policy)
    db.add(w)
    db.flush()
    db.add(WorkspaceMember(workspace_id=w.id, user_id=user.id, role=WorkspaceRole.OWNER))
    audit(db, "workspace_created", user_id=user.id, workspace_id=w.id, entity_type="workspace", entity_id=w.id, request=request)
    return ok(ws_view(w, "OWNER"))


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ctx = resolve_workspace(db, user, workspace_id)
    w = db.get(Workspace, workspace_id)
    members = [
        {"user_id": m.user_id, "name": m.user.name, "email": m.user.email, "role": m.role.value}
        for m in db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == w.id)).scalars()
    ]
    return ok(ws_view(w, ctx.role.value, members))


@router.patch("/{workspace_id}")
def update_workspace(workspace_id: str, body: WorkspacePatch, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ctx = resolve_workspace(db, user, workspace_id)
    ctx.require(WorkspaceRole.ADMIN)
    w = db.get(Workspace, workspace_id)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(w, k, v)
    audit(db, "workspace_setting_changed", user_id=user.id, workspace_id=w.id, entity_type="workspace", entity_id=w.id, request=request, changes=changes)
    return ok(ws_view(w, ctx.role.value))


@router.post("/{workspace_id}/members")
def add_member(workspace_id: str, body: MemberIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ctx = resolve_workspace(db, user, workspace_id)
    ctx.require(WorkspaceRole.ADMIN)
    target = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if not target:
        raise AppError(404, "USER_NOT_FOUND", "No account with that email. Ask them to register first.")
    if db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == target.id)).first():
        raise AppError(409, "ALREADY_MEMBER", "That user is already a member of this workspace.")
    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=WorkspaceRole(body.role)))
    audit(db, "workspace_member_added", user_id=user.id, workspace_id=workspace_id, entity_type="user", entity_id=target.id, request=request, role=body.role)
    return ok({"added": target.email, "role": body.role})
