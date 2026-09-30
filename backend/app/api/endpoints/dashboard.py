"""Workspace dashboard for the application (user side).

Not to be confused with the admin console's system-wide dashboard
(app/api/endpoints/admin_console.py, mounted at /api/admin/overview) — this one
is scoped to the caller's own workspace, like every other endpoint in the app.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, workspace_ctx
from app.core.responses import ok
from app.models.orm import AuditLog, Escalation, Evidence, EvidenceGap, Innovation, PatentFeatureMatch, User

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", summary="Workspace dashboard metrics")
def dashboard(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    ws = ctx.workspace_id
    inn_ids = select(Innovation.id).where(Innovation.workspace_id == ws)
    stats = {
        "total_innovations": db.scalar(select(func.count()).select_from(Innovation).where(Innovation.workspace_id == ws)),
        "active_research": db.scalar(select(func.count()).select_from(Innovation).where(Innovation.workspace_id == ws, Innovation.status.in_(["PROFILED", "IN_RESEARCH"]))),
        "evidence_found": db.scalar(select(func.count()).select_from(Evidence).where(Evidence.innovation_id.in_(inn_ids))),
        "prior_art_matches": db.scalar(select(func.count(func.distinct(PatentFeatureMatch.patent_id))).where(PatentFeatureMatch.innovation_id.in_(inn_ids))),
        "evidence_gaps": db.scalar(select(func.count()).select_from(EvidenceGap).where(EvidenceGap.innovation_id.in_(inn_ids), EvidenceGap.status == "OPEN")),
        "pending_reviews": db.scalar(select(func.count()).select_from(PatentFeatureMatch).where(PatentFeatureMatch.innovation_id.in_(inn_ids), PatentFeatureMatch.review_status == "PENDING")),
        "open_escalations": db.scalar(select(func.count()).select_from(Escalation).where(Escalation.workspace_id == ws, Escalation.status.in_(["OPEN", "IN_REVIEW"]))),
    }
    recent = db.execute(
        select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.user_id).where(AuditLog.workspace_id == ws).order_by(AuditLog.created_at.desc()).limit(12)
    ).all()
    names = {i.id: i.name for i in db.execute(select(Innovation).where(Innovation.workspace_id == ws)).scalars()}
    return ok({
        "stats": stats,
        "recent_activity": [{"action": a.action, "user": n, "entity_type": a.entity_type, "entity_id": a.entity_id,
                             "entity_name": names.get(a.entity_id), "created_at": a.created_at.isoformat()} for a, n in recent],
    })
