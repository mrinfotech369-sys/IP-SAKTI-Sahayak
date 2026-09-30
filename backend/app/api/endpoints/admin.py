"""Dashboard metrics and admin console."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, require_admin, workspace_ctx
from app.core.responses import not_found, ok
from app.models.orm import (
    AuditLog,
    Claim,
    Document,
    DocumentChunk,
    Escalation,
    Evidence,
    EvidenceGap,
    IngestionJob,
    Innovation,
    Message,
    PatentFeatureMatch,
    Source,
    User,
    UserRole,
    Workspace,
    WorkspaceMember,
)
from app.schemas import UserPatch
from app.services.audit import audit
from app.services.governance import purge_expired, runtime_metrics

router = APIRouter(tags=["Dashboard & Admin"])


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


@router.get("/admin/overview", summary="System overview for administrators")
def overview(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    claims = dict(db.execute(select(Claim.support_status, func.count()).group_by(Claim.support_status)).all())
    total_claims = sum(claims.values()) or 1
    answers = db.execute(select(Message.payload).where(Message.role == "assistant").order_by(Message.created_at.desc()).limit(200)).scalars().all()
    latencies = [p.get("trace", {}).get("latency_ms", 0) for p in answers if p]
    abstentions = sum(1 for p in answers if p and p.get("type") == "abstention")
    src_counts = dict(db.execute(select(Document.source_id, func.count()).group_by(Document.source_id)).all())
    return ok({
        "counts": {
            "users": db.scalar(select(func.count()).select_from(User)),
            "workspaces": db.scalar(select(func.count()).select_from(Workspace)),
            "sources": db.scalar(select(func.count()).select_from(Source)),
            "documents": db.scalar(select(func.count()).select_from(Document)),
            "chunks": db.scalar(select(func.count()).select_from(DocumentChunk)),
            "innovations": db.scalar(select(func.count()).select_from(Innovation)),
            "conversations_answers": len(answers),
        },
        "rag_metrics": {
            "answers_sampled": len(answers),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "abstention_rate": round(abstentions / len(answers), 3) if answers else None,
        },
        "citation_metrics": {
            "claims_verified": sum(claims.values()),
            "by_status": {k.value if hasattr(k, "value") else k: v for k, v in claims.items()},
            "unsupported_rate": round(sum(v for k, v in claims.items() if str(getattr(k, "value", k)) in ("UNSUPPORTED", "INSUFFICIENT")) / total_claims, 3),
        },
        "sources": [{"id": s.id, "name": s.name, "tier": s.authority_tier, "jurisdiction": s.jurisdiction, "active": s.active,
                     "last_checked": s.last_checked.isoformat() if s.last_checked else None, "documents": src_counts.get(s.id, 0)}
                    for s in db.execute(select(Source).order_by(Source.authority_tier)).scalars()],
        "runtime": runtime_metrics(db),
        "jobs": {"total": db.scalar(select(func.count()).select_from(IngestionJob)),
                 "failed": db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "FAILED"))},
    })


@router.get("/admin/users")
def users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ws_counts = dict(db.execute(select(WorkspaceMember.user_id, func.count()).group_by(WorkspaceMember.user_id)).all())
    return ok([{"id": u.id, "name": u.name, "email": u.email, "role": u.role.value, "is_active": u.is_active,
                "last_login": u.last_login.isoformat() if u.last_login else None, "workspaces": ws_counts.get(u.id, 0),
                "created_at": u.created_at.isoformat()} for u in db.execute(select(User).order_by(User.created_at)).scalars()])


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, body: UserPatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.role is not None:
        u.role = UserRole(body.role)
    audit(db, "user_modified", user_id=admin.id, entity_type="user", entity_id=u.id, request=request, changes=body.model_dump(exclude_none=True))
    return ok({"id": u.id, "is_active": u.is_active, "role": u.role.value})


@router.get("/admin/workspaces")
def workspaces(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    members = dict(db.execute(select(WorkspaceMember.workspace_id, func.count()).group_by(WorkspaceMember.workspace_id)).all())
    inns = dict(db.execute(select(Innovation.workspace_id, func.count()).group_by(Innovation.workspace_id)).all())
    return ok([{"id": w.id, "name": w.name, "confidential_mode": w.confidential_mode, "retention_policy": w.retention_policy,
                "members": members.get(w.id, 0), "innovations": inns.get(w.id, 0), "created_at": w.created_at.isoformat()}
               for w in db.execute(select(Workspace).order_by(Workspace.created_at)).scalars()])


@router.post("/admin/retention/run", summary="Apply workspace retention policies (dry_run=true only reports)")
def retention_run(request: Request, dry_run: bool = True, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    res = purge_expired(db, dry_run=dry_run)
    audit(db, "retention_purge", user_id=admin.id, entity_type="system", request=request, dry_run=dry_run,
          deleted=sum(w["conversations"] + w["uploaded_documents"] for w in res["workspaces"]) if not dry_run else 0)
    return ok(res)


@router.get("/metrics", summary="Corpus size, latency p50/p95 and cost per query (measured)")
def metrics(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    from app.services.governance import coverage
    return ok({**runtime_metrics(db), "corpus": coverage(db)["corpus"]})
