"""Admin console API. Every route requires an admin-scoped session AND role=ADMIN
(enforced once at router level via `dependencies=[Depends(require_admin)]`)."""
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.api.endpoints.corpus import doc_view, job_view, source_view
from app.api.endpoints.review import esc_view, fb_view
from app.core.config import settings
from app.core.responses import AppError, not_found, ok, recent_errors
from app.models.orm import (
    AuditLog, Claim, ClaimEvidence, Conversation, Document, DocumentChunk, Escalation, EscalationStatus, EvaluationQuestion,
    EvaluationRun, Feedback, IngestionJob, Innovation, Message, Source, SupportStatus, User, UserRole, Workspace, WorkspaceMember,
    WorkspaceRole,
)
from app.schemas import AdminEscalationPatch, DocumentReview, FeedbackPatch, SourceIn, SourcePatch, UserPatch
from app.services.audit import audit
from app.services.embeddings import get_embedder
from app.services.evaluation import run_evaluation
from app.services.governance import _pct, coverage, purge_expired, runtime_metrics, update_queue
from app.services.ingestion import create_job, ocr_available, ocr_languages, process_job
from app.services.llm import data_handling, get_llm

router = APIRouter(prefix="/admin", tags=["Admin console"], dependencies=[Depends(require_admin)])

AUDIT_CATEGORIES = {
    "auth": ("login", "logout", "user_registered", "admin_login", "admin_logout", "password_", "login_failed", "admin_login_failed", "admin_login_denied"),
    "admin": ("user_modified", "retention_purge", "evaluation_run", "document_reindexed", "escalation_assigned", "audit_exported", "feedback_reviewed"),
    "source": ("source_modified",),
    "document": ("document_",),
    "escalation": ("escalation_",),
    "export": ("report_exported", "audit_exported"),
}


def _confidential_workspaces(db: Session) -> set[str]:
    return {w for (w,) in db.execute(select(Workspace.id).where(Workspace.confidential_mode.is_(True))).all()}


def _redact(text: Optional[str], workspace_id: Optional[str], confidential: set[str]) -> Optional[str]:
    """Admins monitor quality, not content: text from confidential workspaces is redacted."""
    if text is None:
        return None
    return "[redacted — confidential workspace]" if workspace_id in confidential else text[:300]


# ---------------------------------------------------------------------------
# Dashboard / analytics / health
# ---------------------------------------------------------------------------

@router.get("/overview", summary="Admin dashboard: counts, system analytics, health")
def overview(db: Session = Depends(get_db)):
    claims = {k.value: v for k, v in db.execute(select(Claim.support_status, func.count()).group_by(Claim.support_status)).all()}
    total_claims = sum(claims.values()) or 1
    week = datetime.now(timezone.utc) - timedelta(days=7)
    llm = get_llm()
    return ok({
        "counts": {
            "users": db.scalar(select(func.count()).select_from(User)),
            "active_users_7d": db.scalar(select(func.count()).select_from(User).where(User.last_login >= week)),
            "workspaces": db.scalar(select(func.count()).select_from(Workspace)),
            "innovations": db.scalar(select(func.count()).select_from(Innovation)),
            "sources": db.scalar(select(func.count()).select_from(Source)),
            "documents": db.scalar(select(func.count()).select_from(Document)),
            "chunks": db.scalar(select(func.count()).select_from(DocumentChunk)),
            "queries": db.scalar(select(func.count()).select_from(Message).where(Message.role == "assistant")),
            "open_escalations": db.scalar(select(func.count()).select_from(Escalation).where(Escalation.status.in_(["OPEN", "IN_REVIEW"]))),
            "open_feedback": db.scalar(select(func.count()).select_from(Feedback).where(Feedback.status.in_(["OPEN", "IN_REVIEW"]))),
            "sources_due_review": len(update_queue(db)),
            "failed_ingestion_jobs": db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "FAILED")),
        },
        "citations": {"by_status": claims, "unsupported_rate": round((claims.get("UNSUPPORTED", 0) + claims.get("INSUFFICIENT", 0)) / total_claims, 3)},
        "runtime": runtime_metrics(db),
        "llm": {"provider": llm.name, "available": llm.available},
        "recent_errors": recent_errors()[:10],
    })


@router.get("/metrics", summary="Latency p50/p95, cost per query, corpus size (measured)")
def metrics(db: Session = Depends(get_db)):
    return ok({**runtime_metrics(db), "corpus": coverage(db)["corpus"]})


@router.get("/settings", summary="Effective configuration (secrets masked)")
def settings_view():
    mask = lambda v: ("set (" + str(len(v)) + " chars)") if v else "not set"
    return ok({
        "environment": settings.APP_ENV,
        "llm": {"provider": settings.LLM_PROVIDER, "model": settings.llm_model, "base_url": settings.LLM_BASE_URL or "provider default",
                "api_key": mask(settings.LLM_API_KEY), "temperature": settings.LLM_TEMPERATURE, "max_tokens": settings.LLM_MAX_TOKENS,
                "timeout_s": settings.LLM_TIMEOUT_SECONDS, "data_handling": data_handling()["policy"]},
        "embeddings": {"provider": settings.EMBEDDING_PROVIDER, "active": get_embedder().name, "dimension": settings.EMBEDDING_DIMENSION},
        "retrieval": {"top_k": settings.RETRIEVAL_TOP_K, "candidates": settings.RETRIEVAL_CANDIDATES, "min_evidence_score": settings.MIN_EVIDENCE_SCORE},
        "rate_limits_per_min": {"chat": settings.RATE_LIMIT_CHAT, "search": settings.RATE_LIMIT_SEARCH, "ingest": settings.RATE_LIMIT_INGEST,
                                "report": settings.RATE_LIMIT_REPORT, "login_attempts": settings.LOGIN_ATTEMPTS_PER_MINUTE},
        "sessions": {"user_ttl_min": settings.ACCESS_TOKEN_TTL_MINUTES, "admin_ttl_min": settings.ADMIN_SESSION_TTL_MINUTES,
                     "jwt_secret": mask(settings.JWT_SECRET if not settings.JWT_SECRET.startswith("dev-only") else "")},
        "uploads": {"max_mb": settings.MAX_UPLOAD_MB, "ocr": ocr_languages() if ocr_available() else "not installed"},
        "cost_assumptions_usd_per_million": {"input": settings.LLM_PRICE_INPUT_PER_M, "output": settings.LLM_PRICE_OUTPUT_PER_M},
        "how_to_change": "Edit .env on the server and restart the backend (scripts/stop_all.sh && scripts/start_all.sh). Secrets are never shown here.",
    })


@router.post("/retention/run", summary="Apply workspace retention policies (dry_run=true only reports)")
def retention_run(request: Request, dry_run: bool = True, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    res = purge_expired(db, dry_run=dry_run)
    audit(db, "retention_purge", user_id=admin.id, entity_type="system", request=request, dry_run=dry_run,
          deleted=0 if dry_run else sum(w["conversations"] + w["uploaded_documents"] for w in res["workspaces"]))
    return ok(res)


# ---------------------------------------------------------------------------
# Users & workspaces
# ---------------------------------------------------------------------------

@router.get("/users")
def users(q: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(User)
    if q:
        like = f"%{q.strip()[:100]}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.name.ilike(like)))
    if role in ("ADMIN", "USER"):
        stmt = stmt.where(User.role == UserRole(role))
    if status in ("active", "disabled"):
        stmt = stmt.where(User.is_active.is_(status == "active"))
    members = db.execute(select(WorkspaceMember, Workspace.name).join(Workspace, Workspace.id == WorkspaceMember.workspace_id)).all()
    by_user: dict[str, list] = {}
    for m, wname in members:
        by_user.setdefault(m.user_id, []).append({"workspace": wname, "role": m.role.value})
    return ok([{"id": u.id, "name": u.name, "email": u.email, "role": u.role.value, "is_active": u.is_active,
                "last_login": u.last_login.isoformat() if u.last_login else None, "workspaces": by_user.get(u.id, []),
                "created_at": u.created_at.isoformat()} for u in db.execute(stmt.order_by(User.created_at)).scalars()])


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserPatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    if u.id == admin.id and (body.is_active is False or body.role == "USER"):
        raise AppError(409, "SELF_LOCKOUT", "You cannot disable or demote your own admin account.")
    if body.role == "USER" and u.role == UserRole.ADMIN:
        remaining = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != u.id))
        if not remaining:
            raise AppError(409, "LAST_ADMIN", "At least one active administrator must remain.")
    changes = body.model_dump(exclude_none=True)
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.role is not None:
        u.role = UserRole(body.role)
    audit(db, "user_modified", user_id=admin.id, entity_type="user", entity_id=u.id, request=request, changes=changes, target=u.email)
    return ok({"id": u.id, "is_active": u.is_active, "role": u.role.value})


@router.get("/workspaces")
def workspaces(db: Session = Depends(get_db)):
    members = dict(db.execute(select(WorkspaceMember.workspace_id, func.count()).group_by(WorkspaceMember.workspace_id)).all())
    inns = dict(db.execute(select(Innovation.workspace_id, func.count()).group_by(Innovation.workspace_id)).all())
    return ok([{"id": w.id, "name": w.name, "confidential_mode": w.confidential_mode, "retention_policy": w.retention_policy,
                "members": members.get(w.id, 0), "innovations": inns.get(w.id, 0), "created_at": w.created_at.isoformat()}
               for w in db.execute(select(Workspace).order_by(Workspace.created_at)).scalars()])


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Document.source_id, func.count()).group_by(Document.source_id)).all())
    return ok([source_view(s, counts.get(s.id, 0)) for s in db.execute(select(Source).order_by(Source.authority_tier, Source.name)).scalars()])


@router.post("/sources", summary="Register a source")
def create_source(body: SourceIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = Source(**body.model_dump(), last_checked=None)
    db.add(s)
    db.flush()
    audit(db, "source_modified", user_id=admin.id, entity_type="source", entity_id=s.id, request=request, change="created", name=s.name)
    return ok(source_view(s))


@router.patch("/sources/{source_id}", summary="Edit / disable a source, set tier, jurisdiction, URL, freshness")
def update_source(source_id: str, body: SourcePatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise not_found("Source")
    changes = body.model_dump(exclude_none=True)
    mark = changes.pop("mark_checked", False)
    for k, v in changes.items():
        setattr(s, k, v)
    if mark:
        s.last_checked = datetime.now(timezone.utc)
    audit(db, "source_modified", user_id=admin.id, entity_type="source", entity_id=s.id, request=request,
          changes=sorted(changes) + (["last_checked"] if mark else []), name=s.name)
    return ok(source_view(s))


# ---------------------------------------------------------------------------
# Documents & ingestion
# ---------------------------------------------------------------------------

@router.get("/documents")
def documents(q: Optional[str] = None, domain: Optional[str] = None, jurisdiction: Optional[str] = None, status: Optional[str] = None,
              scope: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(Document)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q[:100]}%"))
    if domain:
        stmt = stmt.where(Document.domain == domain)
    if jurisdiction:
        stmt = stmt.where(Document.jurisdiction == jurisdiction)
    if status:
        stmt = stmt.where(Document.review_status == status)
    if scope == "global":
        stmt = stmt.where(Document.workspace_id.is_(None))
    elif scope == "workspace":
        stmt = stmt.where(Document.workspace_id.is_not(None))
    counts = dict(db.execute(select(DocumentChunk.document_id, func.count()).group_by(DocumentChunk.document_id)).all())
    embedded = dict(db.execute(select(DocumentChunk.document_id, func.count()).where(DocumentChunk.embedding.is_not(None)).group_by(DocumentChunk.document_id)).all())
    wsn = {w.id: w.name for w in db.execute(select(Workspace)).scalars()}
    out = []
    for d in db.execute(stmt.order_by(Document.created_at.desc())).scalars():
        out.append({**doc_view(d, counts.get(d.id, 0)), "indexed_chunks": embedded.get(d.id, 0), "workspace": wsn.get(d.workspace_id)})
    return ok(out)


@router.get("/documents/{document_id}")
def document(document_id: str, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d:
        raise not_found("Document")
    chunks = db.execute(select(DocumentChunk).where(DocumentChunk.document_id == d.id).order_by(DocumentChunk.chunk_index)).scalars().all()
    private = d.workspace_id is not None
    jobs = db.execute(select(IngestionJob).where(IngestionJob.document_id == d.id)).scalars().all()
    audit(db, "document_viewed", user_id=admin.id, entity_type="document", entity_id=d.id, request=request, console="admin")
    return ok({
        **doc_view(d, len(chunks)), "metadata": d.metadata_, "workspace_private": private,
        "extraction": {"method": d.extraction_method, "ocr_confidence": d.ocr_confidence, "jobs": [job_view(j) for j in jobs],
                       "indexed_chunks": sum(1 for c in chunks if c.embedding is not None),
                       "injection_flagged_chunks": sum(1 for c in chunks if c.injection_flag)},
        # Workspace uploads belong to that workspace: admins see metadata and status, not the content.
        "chunks": [{"id": c.id, "index": c.chunk_index, "section": c.section, "chunk_type": c.chunk_type, "injection_flag": c.injection_flag,
                    "content": None if private else c.content} for c in chunks],
    })


@router.post("/documents/ingest", summary="Ingest an official document into the global corpus")
async def ingest_document(request: Request, background: BackgroundTasks, file: UploadFile = File(...), title: str = Form(..., min_length=2, max_length=500),
                          source_id: str = Form(...), jurisdiction: str = Form(...), domain: str = Form(...), document_type: str = Form(...),
                          language: str = Form("en"), publication_date: Optional[str] = Form(None), effective_date: Optional[str] = Form(None),
                          url: Optional[str] = Form(None), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    data = await file.read()
    meta = {"title": title, "jurisdiction": jurisdiction, "domain": domain, "document_type": document_type, "language": language,
            "publication_date": publication_date, "effective_date": effective_date, "url": url}
    try:
        job = create_job(db, filename=file.filename or "upload", data=data, meta=meta, source_id=source_id, workspace_id=None, user_id=admin.id)
    except AppError as exc:
        db.rollback()
        db.add(IngestionJob(source_id=source_id, file_name=(file.filename or "upload")[:300], status="FAILED", error=f"{exc.code}: {exc.message}",
                            created_by=admin.id, finished_at=datetime.now(timezone.utc), steps=[{"step": "failed", "error": exc.code}]))
        audit(db, "document_ingest_failed", user_id=admin.id, entity_type="ingestion", request=request, error=exc.code, scope="global")
        raise
    audit(db, "document_ingest_queued", user_id=admin.id, entity_type="ingestion", entity_id=job.id, request=request, scope="global")
    background.add_task(process_job, job.id, meta)
    return ok({"job": job_view(job)})


@router.patch("/documents/{document_id}/review", summary="Mark checked, approve (verified), reject, restore or mark superseded")
def review_document(document_id: str, body: DocumentReview, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d:
        raise not_found("Document")
    now = datetime.now(timezone.utc)
    if body.action == "mark_checked":
        d.last_checked = now
    elif body.action == "approve":
        d.review_status, d.last_checked = "VERIFIED", now
    elif body.action == "reject":
        d.review_status = "REJECTED"  # excluded from retrieval
    elif body.action == "restore":
        d.review_status = "PENDING_REVIEW"
    elif body.action == "mark_superseded":
        new = db.get(Document, body.superseded_by or "")
        if not new:
            raise AppError(422, "SUPERSEDING_DOCUMENT_REQUIRED", "Give the id of the document that supersedes this one.")
        d.superseded_by_document_id, new.supersedes_document_id = new.id, d.id
    if body.version:
        d.version = body.version
    if body.effective_date:
        d.effective_date = body.effective_date
    audit(db, "document_reviewed", user_id=admin.id, entity_type="document", entity_id=d.id, request=request, review_action=body.action, note=body.note)
    return ok(doc_view(d))


@router.post("/documents/{document_id}/reindex", summary="Re-embed all chunks with the current embedding provider")
def reindex_document(document_id: str, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d:
        raise not_found("Document")
    chunks = db.execute(select(DocumentChunk).where(DocumentChunk.document_id == d.id).order_by(DocumentChunk.chunk_index)).scalars().all()
    emb = get_embedder()
    texts = [f"{c.section or ''} {c.subsection or ''}: {c.content}" if d.extraction_method == "STRUCTURED_SEED" else c.content for c in chunks]
    for c, v in zip(chunks, emb.embed_batch(texts)):
        c.embedding = v
    audit(db, "document_reindexed", user_id=admin.id, entity_type="document", entity_id=d.id, request=request, chunks=len(chunks), provider=emb.name)
    return ok({"document_id": d.id, "reindexed_chunks": len(chunks), "embedding_provider": emb.name})


@router.get("/ingestion-jobs")
def ingestion_jobs(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(IngestionJob)
    if status:
        q = q.where(IngestionJob.status == status)
    return ok([job_view(j) for j in db.execute(q.order_by(IngestionJob.created_at.desc()).limit(200)).scalars()])


@router.get("/update-queue", summary="Documents due for re-checking, by source update frequency")
def admin_update_queue(db: Session = Depends(get_db)):
    return ok(update_queue(db))


# ---------------------------------------------------------------------------
# RAG & citation monitoring
# ---------------------------------------------------------------------------

@router.get("/rag", summary="Retrieval statistics, failed retrievals, abstentions, latency, errors")
def rag_monitoring(days: int = 30, db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), 365))
    conf = _confidential_workspaces(db)
    rows = db.execute(
        select(Message, Conversation.workspace_id).join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.role == "assistant", Message.created_at >= since).order_by(Message.created_at.desc())
    ).all()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    by_intent: dict[str, int] = {}
    reasons: dict[str, int] = {}
    lat, failed, abstentions, llm_fallbacks = [], [], [], 0
    for m, ws in rows:
        p = m.payload or {}
        t = p.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        by_status[p.get("evidence_status", "?")] = by_status.get(p.get("evidence_status", "?"), 0) + 1
        mode = (p.get("generation") or {}).get("mode", "?")
        by_mode[mode] = by_mode.get(mode, 0) + 1
        intent = (p.get("analysis") or {}).get("intent", "?")
        by_intent[intent] = by_intent.get(intent, 0) + 1
        if "Language model unavailable" in (p.get("answer") or ""):
            llm_fallbacks += 1
        if (p.get("trace") or {}).get("latency_ms") is not None:
            lat.append(p["trace"]["latency_ms"])
        safety = next((s.get("result") for s in (p.get("trace") or {}).get("pipeline", []) if s.get("step") == "safety_abstention"), None)
        if t in ("abstention", "clarification"):
            reason = safety or ("CLAIMS_NOT_VERIFIED" if p.get("evidence") else "NO_EVIDENCE")
            reasons[reason] = reasons.get(reason, 0) + 1
            item = {"at": m.created_at.isoformat(), "reason": reason, "intent": intent, "jurisdiction": (p.get("analysis") or {}).get("jurisdiction_label"),
                    "question": _redact((p.get("trace") or {}).get("retrieval", {}).get("query") or p.get("search_query"), ws, conf),
                    "missing": (p.get("abstention") or {}).get("missing")}
            (failed if reason == "NO_EVIDENCE" else abstentions).append(item)
    n = len(rows) or 1
    return ok({
        "window_days": days, "queries": len(rows),
        "by_type": by_type, "by_evidence_status": by_status, "by_generation_mode": by_mode, "by_intent": by_intent,
        "abstention_reasons": reasons, "abstention_rate": round(sum(reasons.values()) / n, 3),
        "failed_retrieval_rate": round(reasons.get("NO_EVIDENCE", 0) / n, 3),
        "latency_ms": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "max": max(lat) if lat else None},
        "llm_fallbacks": llm_fallbacks,
        "failed_retrievals": failed[:50], "abstentions": abstentions[:50],
        "system_errors": recent_errors(),
        "privacy_note": "Questions from confidential workspaces are redacted.",
    })


@router.get("/citations", summary="Citation verification monitoring")
def citation_monitoring(days: int = 30, db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), 365))
    conf = _confidential_workspaces(db)
    by_status = {k.value: v for k, v in db.execute(select(Claim.support_status, func.count()).where(Claim.created_at >= since).group_by(Claim.support_status)).all()}
    by_type = dict(db.execute(select(Claim.claim_type, func.count()).where(Claim.created_at >= since).group_by(Claim.claim_type)).all())
    total = sum(by_status.values()) or 1
    bad = db.execute(
        select(Claim, Conversation.workspace_id).outerjoin(Conversation, Conversation.id == Claim.conversation_id)
        .where(Claim.created_at >= since, Claim.support_status.in_([SupportStatus.UNSUPPORTED, SupportStatus.CONFLICTING, SupportStatus.INSUFFICIENT]))
        .order_by(Claim.created_at.desc()).limit(100)
    ).all()
    failures = []
    for c, ws in bad:
        ev = db.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == c.id)).scalars().first()
        doc = None
        if ev and ev.chunk_id:
            ch = db.get(DocumentChunk, ev.chunk_id)
            doc = ch.document.title if ch else None
        failures.append({"at": c.created_at.isoformat(), "status": c.support_status.value, "claim_type": c.claim_type,
                         "claim": _redact(c.claim_text, ws, conf), "cited_document": doc,
                         "score": ev.entailment_score if ev else None, "notes": ev.notes if ev else None,
                         "llm_entailment": (ev.checks or {}).get("llm_entailment") if ev else None})
    return ok({
        "window_days": days, "claims": sum(by_status.values()), "by_status": by_status, "by_claim_type": by_type,
        "supported_rate": round(by_status.get("SUPPORTED", 0) / total, 3),
        "unsupported_rate": round((by_status.get("UNSUPPORTED", 0) + by_status.get("INSUFFICIENT", 0)) / total, 3),
        "conflicting_rate": round(by_status.get("CONFLICTING", 0) / total, 3),
        "failures": failures,
    })


# ---------------------------------------------------------------------------
# Escalations & feedback
# ---------------------------------------------------------------------------

def _esc_admin_view(db: Session, e: Escalation, full: bool = False) -> dict:
    inn = db.get(Innovation, e.innovation_id)
    ws = db.get(Workspace, e.workspace_id)
    assignee = db.get(User, e.assigned_to) if e.assigned_to else None
    return {**esc_view(e, full=full), "innovation_name": inn.name if inn else None, "workspace": ws.name if ws else None,
            "assigned_to": {"id": assignee.id, "name": assignee.name, "email": assignee.email} if assignee else None,
            "reviewer_notes": e.reviewer_notes or []}


@router.get("/escalations")
def escalations(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(Escalation)
    if status:
        q = q.where(Escalation.status == EscalationStatus(status))
    return ok([_esc_admin_view(db, e) for e in db.execute(q.order_by(Escalation.created_at.desc()).limit(200)).scalars()])


@router.get("/escalations/{escalation_id}")
def escalation(escalation_id: str, db: Session = Depends(get_db)):
    e = db.get(Escalation, escalation_id)
    if not e:
        raise not_found("Escalation")
    reviewers = db.execute(
        select(User).join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == e.workspace_id, User.is_active.is_(True),
               WorkspaceMember.role.in_([WorkspaceRole.REVIEWER, WorkspaceRole.ADMIN, WorkspaceRole.OWNER]))
    ).scalars().all()
    return ok({**_esc_admin_view(db, e, full=True), "eligible_reviewers": [{"id": u.id, "name": u.name, "email": u.email} for u in reviewers]})


@router.patch("/escalations/{escalation_id}", summary="Assign reviewer, update status, add reviewer note")
def update_escalation(escalation_id: str, body: AdminEscalationPatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = db.get(Escalation, escalation_id)
    if not e:
        raise not_found("Escalation")
    if body.assigned_to:
        ok_member = db.execute(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == e.workspace_id, WorkspaceMember.user_id == body.assigned_to,
            WorkspaceMember.role.in_([WorkspaceRole.REVIEWER, WorkspaceRole.ADMIN, WorkspaceRole.OWNER]))).first()
        if not ok_member:
            raise AppError(422, "INELIGIBLE_REVIEWER", "Reviewer must be a Reviewer, Admin or Owner of the escalation's workspace.")
        e.assigned_to = body.assigned_to
        audit(db, "escalation_assigned", user_id=admin.id, workspace_id=e.workspace_id, entity_type="innovation", entity_id=e.innovation_id,
              request=request, commit=False, escalation_id=e.id, assigned_to=body.assigned_to)
    if body.unassign:
        e.assigned_to = None
    if body.status:
        e.status = EscalationStatus(body.status)
        audit(db, "escalation_status_changed", user_id=admin.id, workspace_id=e.workspace_id, entity_type="innovation", entity_id=e.innovation_id,
              request=request, commit=False, escalation_id=e.id, status=body.status)
    if body.note:
        e.reviewer_notes = [*(e.reviewer_notes or []), {"by": admin.name, "at": datetime.now(timezone.utc).isoformat(), "note": body.note}]
        audit(db, "escalation_note_added", user_id=admin.id, workspace_id=e.workspace_id, entity_type="innovation", entity_id=e.innovation_id,
              request=request, commit=False, escalation_id=e.id)
    db.commit()
    return ok(_esc_admin_view(db, e))


@router.get("/feedback")
def feedback(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(Feedback)
    if status:
        q = q.where(Feedback.status == status)
    wsn = {w.id: w.name for w in db.execute(select(Workspace)).scalars()}
    return ok([{**fb_view(f), "workspace": wsn.get(f.workspace_id)} for f in db.execute(q.order_by(Feedback.created_at.desc()).limit(200)).scalars()])


@router.patch("/feedback/{feedback_id}")
def review_feedback(feedback_id: str, body: FeedbackPatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    f = db.get(Feedback, feedback_id)
    if not f:
        raise not_found("Feedback")
    f.status, f.resolution_note, f.reviewed_by = body.status, body.resolution_note, admin.id
    audit(db, "feedback_reviewed", user_id=admin.id, workspace_id=f.workspace_id, entity_type="feedback", entity_id=f.id, request=request, status=body.status)
    return ok(fb_view(f))


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------

def _audit_query(category: Optional[str], action: Optional[str], user: Optional[str], entity_id: Optional[str], days: int):
    q = select(AuditLog, User.name, User.email).outerjoin(User, User.id == AuditLog.user_id)
    q = q.where(AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), 3650)))
    if category in AUDIT_CATEGORIES:
        q = q.where(or_(*[AuditLog.action.startswith(p) for p in AUDIT_CATEGORIES[category]]))
    if action:
        q = q.where(AuditLog.action == action)
    if user:
        q = q.where(or_(User.email.ilike(f"%{user[:100]}%"), User.name.ilike(f"%{user[:100]}%")))
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    return q.order_by(AuditLog.created_at.desc())


@router.get("/audit-logs")
def audit_logs(category: Optional[str] = None, action: Optional[str] = None, user: Optional[str] = None, entity_id: Optional[str] = None,
               days: int = 30, limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.execute(_audit_query(category, action, user, entity_id, days).limit(min(limit, 500)).offset(max(offset, 0))).all()
    wsn = {w.id: w.name for w in db.execute(select(Workspace)).scalars()}
    return ok([{"id": a.id, "action": a.action, "user": name, "email": email, "workspace": wsn.get(a.workspace_id), "entity_type": a.entity_type,
                "entity_id": a.entity_id, "metadata": a.metadata_, "request_id": a.request_id, "created_at": a.created_at.isoformat()}
               for a, name, email in rows], categories=list(AUDIT_CATEGORIES))


@router.get("/audit-logs/export", summary="Export audit logs as CSV")
def audit_export(request: Request, category: Optional[str] = None, action: Optional[str] = None, user: Optional[str] = None, days: int = 30,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(_audit_query(category, action, user, None, days).limit(10000)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "action", "user", "email", "workspace_id", "entity_type", "entity_id", "request_id", "metadata"])
    for a, name, email in rows:
        w.writerow([a.created_at.isoformat(), a.action, name or "", email or "", a.workspace_id or "", a.entity_type or "", a.entity_id or "",
                    a.request_id or "", a.metadata_])
    audit(db, "audit_exported", user_id=admin.id, entity_type="audit", request=request, rows=len(rows), category=category)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="audit-{datetime.now(timezone.utc):%Y%m%d}.csv"'})


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def run_view(r: EvaluationRun) -> dict:
    return {"id": r.id, "metrics": r.metrics, "results": r.results, "llm_provider": r.llm_provider,
            "embedding_provider": r.embedding_provider, "created_at": r.created_at.isoformat()}


@router.get("/evaluations", summary="Latest evaluation run, history and question set")
def evaluations(db: Session = Depends(get_db)):
    run = db.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(1)).scalar_one_or_none()
    history = db.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(10)).scalars().all()
    qs = db.execute(select(EvaluationQuestion).order_by(EvaluationQuestion.key)).scalars().all()
    return ok({
        "latest": run_view(run) if run else None,
        "history": [{"id": h.id, "created_at": h.created_at.isoformat(), "metrics": h.metrics, "llm_provider": h.llm_provider} for h in history],
        "questions": [{"key": q.key, "category": q.category, "question": q.question, "language": q.language, "jurisdiction": q.jurisdiction,
                       "expected_abstention": q.expected_abstention} for q in qs],
    })


@router.post("/evaluations/run", summary="Run the evaluation suite against the live pipeline")
def run_eval(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ws = db.execute(select(Workspace.id).limit(1)).scalar()
    r = run_evaluation(db, ws)
    audit(db, "evaluation_run", user_id=admin.id, entity_type="evaluation", entity_id=r.id, request=request,
          passed=r.metrics.get("passed"), questions=r.metrics.get("questions"))
    return ok(run_view(r))
