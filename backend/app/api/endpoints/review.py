"""Human escalation, evidence reports and the audit trail."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, rate_limit, resolve_workspace, workspace_ctx
from app.core.responses import not_found, ok
from app.models.orm import (
    AuditLog, Conversation, Escalation, EscalationStatus, EscalationType, Feedback, Innovation, InnovationStatus, Message, Report, User,
    UserRole, WorkspaceRole,
)
from app.schemas import EscalationIn, EscalationPatch, FeedbackIn, FeedbackPatch, ReportIn
from app.services.audit import audit
from app.services.packets import PROFESSIONAL, build_packet, build_report

router = APIRouter(tags=["Review, Reports & Audit"])


def _innovation(db: Session, ctx: WorkspaceCtx, innovation_id: str) -> tuple[WorkspaceCtx, Innovation]:
    inn = db.get(Innovation, innovation_id)
    if not inn:
        raise not_found("Innovation")
    if inn.workspace_id != ctx.workspace_id:
        ctx = resolve_workspace(db, ctx.user, inn.workspace_id)
    return ctx, inn


def esc_view(e: Escalation, full: bool = False) -> dict:
    d = {"id": e.id, "innovation_id": e.innovation_id, "type": e.type.value, "reason": e.reason, "summary": e.summary,
         "open_questions": e.open_questions, "recommended_professional": e.recommended_professional, "status": e.status.value,
         "created_at": e.created_at.isoformat(), "updated_at": e.updated_at.isoformat()}
    if full:
        d["packet"] = e.packet
    return d


@router.post("/escalations", summary="Create a human-review escalation with a full evidence packet")
def create_escalation(body: EscalationIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    ctx, inn = _innovation(db, ctx, body.innovation_id)
    ctx.require(WorkspaceRole.RESEARCHER)
    packet = build_packet(db, inn)
    etype = EscalationType(body.type)
    e = Escalation(
        innovation_id=inn.id, workspace_id=inn.workspace_id, type=etype, reason=body.reason,
        summary=f"{etype.value.replace('_', ' ').title()} requested for {inn.name}: {len(packet['evidence_gaps'])} gaps, "
                f"{len(packet['patent_findings']['families'])} patent families, {len(packet['conflicting_sources'])} conflicts.",
        open_questions=packet["open_questions"][:20], recommended_professional=PROFESSIONAL[etype], packet=packet, created_by=ctx.user.id,
    )
    db.add(e)
    if inn.status != InnovationStatus.COMPLETED:
        inn.status = InnovationStatus.IN_REVIEW
    db.flush()
    audit(db, "escalation_created", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request,
          escalation_id=e.id, type=etype.value)
    return ok(esc_view(e, full=True))


@router.get("/escalations")
def list_escalations(innovation_id: str | None = None, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    q = select(Escalation).where(Escalation.workspace_id == ctx.workspace_id)
    if innovation_id:
        q = q.where(Escalation.innovation_id == innovation_id)
    rows = db.execute(q.order_by(Escalation.created_at.desc())).scalars().all()
    names = {i.id: i.name for i in db.execute(select(Innovation).where(Innovation.workspace_id == ctx.workspace_id)).scalars()}
    return ok([{**esc_view(e), "innovation_name": names.get(e.innovation_id)} for e in rows])


@router.get("/escalations/{escalation_id}")
def get_escalation(escalation_id: str, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    e = db.get(Escalation, escalation_id)
    if not e:
        raise not_found("Escalation")
    resolve_workspace(db, ctx.user, e.workspace_id)
    return ok(esc_view(e, full=True))


@router.patch("/escalations/{escalation_id}")
def update_escalation(escalation_id: str, body: EscalationPatch, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    e = db.get(Escalation, escalation_id)
    if not e:
        raise not_found("Escalation")
    rctx = resolve_workspace(db, ctx.user, e.workspace_id)
    rctx.require(WorkspaceRole.REVIEWER)
    e.status = EscalationStatus(body.status)
    audit(db, "escalation_status_changed", user_id=ctx.user.id, workspace_id=e.workspace_id, entity_type="innovation", entity_id=e.innovation_id,
          request=request, escalation_id=e.id, status=body.status)
    return ok(esc_view(e))


def report_view(r: Report, full: bool = True) -> dict:
    d = {"id": r.id, "innovation_id": r.innovation_id, "title": r.title, "created_at": r.created_at.isoformat()}
    if full:
        d.update({"content": r.content, "markdown": r.markdown})
    return d


@router.post("/reports", dependencies=[Depends(rate_limit("report"))], summary="Generate an evidence report")
def create_report(body: ReportIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    ctx, inn = _innovation(db, ctx, body.innovation_id)
    ctx.require(WorkspaceRole.RESEARCHER)
    content, md = build_report(db, inn)
    r = Report(innovation_id=inn.id, workspace_id=inn.workspace_id, title=content["title"], content=content, markdown=md, created_by=ctx.user.id)
    db.add(r)
    db.flush()
    audit(db, "report_generated", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, report_id=r.id)
    return ok(report_view(r))


@router.get("/reports")
def list_reports(innovation_id: str | None = None, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    q = select(Report).where(Report.workspace_id == ctx.workspace_id)
    if innovation_id:
        q = q.where(Report.innovation_id == innovation_id)
    return ok([report_view(r, full=False) for r in db.execute(q.order_by(Report.created_at.desc())).scalars()])


def _report(db: Session, ctx: WorkspaceCtx, report_id: str) -> Report:
    r = db.get(Report, report_id)
    if not r:
        raise not_found("Report")
    resolve_workspace(db, ctx.user, r.workspace_id)
    return r


@router.get("/reports/{report_id}")
def get_report(report_id: str, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    return ok(report_view(_report(db, ctx, report_id)))


@router.get("/reports/{report_id}/markdown", response_class=PlainTextResponse, summary="Download report as Markdown")
def report_markdown(report_id: str, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    r = _report(db, ctx, report_id)
    audit(db, "report_exported", user_id=ctx.user.id, workspace_id=r.workspace_id, entity_type="innovation", entity_id=r.innovation_id, request=request, format="markdown")
    fname = "".join(ch if ch.isalnum() else "-" for ch in r.title)[:80] + ".md"
    return PlainTextResponse(r.markdown, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/audit", summary="Audit trail for the current workspace")
def audit_trail(entity_id: str | None = None, action: str | None = None, limit: int = 200,
                ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    q = select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.user_id).where(AuditLog.workspace_id == ctx.workspace_id)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if action:
        q = q.where(AuditLog.action == action)
    rows = db.execute(q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return ok([{"id": a.id, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "metadata": a.metadata_,
                "user": name, "created_at": a.created_at.isoformat(), "request_id": a.request_id} for a, name in rows])


# ---------------------------------------------------------------------------
# Feedback: report an answer / source / citation issue, with a review workflow
# ---------------------------------------------------------------------------

def fb_view(f: Feedback) -> dict:
    return {"id": f.id, "category": f.category, "reason": f.reason, "target": f.target, "snapshot": f.snapshot, "status": f.status,
            "resolution_note": f.resolution_note, "message_id": f.message_id, "innovation_id": f.innovation_id,
            "created_at": f.created_at.isoformat(), "updated_at": f.updated_at.isoformat()}


@router.post("/feedback", summary="Report a wrong answer, source or citation")
def create_feedback(body: FeedbackIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    snapshot: dict = {}
    if body.message_id:
        m = db.get(Message, body.message_id)
        conv = db.get(Conversation, m.conversation_id) if m else None
        if not m or not conv or conv.workspace_id != ctx.workspace_id:
            raise not_found("Message")
        p = m.payload or {}
        snapshot = {
            "answer": p.get("answer"), "type": p.get("type"), "evidence_status": p.get("evidence_status"),
            "confidence": (p.get("confidence") or {}).get("score"), "key_points": [{k: kp.get(k) for k in ("id", "text", "status", "citations")} for kp in p.get("key_points", [])],
            "sources": [{k: e.get(k) for k in ("n", "chunk_id", "title", "section", "version", "effective_date", "last_checked", "review_status")} for e in p.get("evidence", [])],
            "generation": p.get("generation"), "captured_at": m.created_at.isoformat(),
        }
        m.flagged = True
    f = Feedback(workspace_id=ctx.workspace_id, user_id=ctx.user.id, message_id=body.message_id, innovation_id=body.innovation_id,
                 category=body.category, reason=body.reason, target=body.target, snapshot=snapshot)
    db.add(f)
    db.flush()
    audit(db, "feedback_submitted", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="feedback", entity_id=f.id, request=request,
          category=body.category)
    return ok(fb_view(f))


@router.get("/feedback")
def list_feedback(status: str | None = None, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    q = select(Feedback)
    if ctx.user.role != UserRole.ADMIN:
        q = q.where(Feedback.workspace_id == ctx.workspace_id)
    if status:
        q = q.where(Feedback.status == status)
    return ok([fb_view(f) for f in db.execute(q.order_by(Feedback.created_at.desc()).limit(200)).scalars()])


@router.patch("/feedback/{feedback_id}")
def review_feedback(feedback_id: str, body: FeedbackPatch, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    f = db.get(Feedback, feedback_id)
    if not f:
        raise not_found("Feedback")
    rctx = resolve_workspace(db, ctx.user, f.workspace_id) if ctx.user.role != UserRole.ADMIN else ctx
    rctx.require(WorkspaceRole.REVIEWER)
    f.status = body.status
    f.resolution_note = body.resolution_note
    f.reviewed_by = ctx.user.id
    audit(db, "feedback_reviewed", user_id=ctx.user.id, workspace_id=f.workspace_id, entity_type="feedback", entity_id=f.id, request=request, status=body.status)
    return ok(fb_view(f))
