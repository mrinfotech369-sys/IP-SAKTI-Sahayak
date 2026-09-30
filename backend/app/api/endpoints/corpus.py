"""Source registry, documents and ingestion."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, rate_limit, require_admin, workspace_ctx
from app.core.responses import AppError, not_found, ok
from app.models.orm import Document, DocumentChunk, IngestionJob, Source, User, UserRole, WorkspaceRole
from app.core.config import settings
from app.schemas import DocumentReview, SourceIn, SourcePatch
from app.services.audit import audit
from app.services.governance import coverage, update_queue, update_status
from app.services.ingestion import create_job, ocr_available, process_job
from app.services.llm import data_handling
from app.services.retrieval import freshness_status

router = APIRouter(tags=["Sources & Documents"])


def source_view(s: Source, docs: int = 0) -> dict:
    return {"id": s.id, "name": s.name, "authority": s.authority, "authority_tier": s.authority_tier, "jurisdiction": s.jurisdiction,
            "source_type": s.source_type, "base_url": s.base_url, "access_level": s.access_level, "description": s.description,
            "active": s.active, "last_checked": s.last_checked.isoformat() if s.last_checked else None,
            "status": freshness_status(s.last_checked, False), "documents": docs,
            "update_frequency_days": s.update_frequency_days, "curator": s.curator,
            "update_status": update_status(s.last_checked, s.update_frequency_days)}


def doc_view(d: Document, chunks: int | None = None) -> dict:
    return {"id": d.id, "title": d.title, "source_id": d.source_id, "source": d.source.name, "authority": d.source.authority,
            "tier": d.source.authority_tier, "document_type": d.document_type, "domain": d.domain, "jurisdiction": d.jurisdiction,
            "publication_date": d.publication_date, "effective_date": d.effective_date,
            "last_checked": d.last_checked.isoformat() if d.last_checked else None, "version": d.version, "language": d.language,
            "url": d.url, "access_level": d.access_level, "content_hash": d.content_hash, "extraction_method": d.extraction_method,
            "ocr_confidence": d.ocr_confidence, "review_status": d.review_status, "is_demo": d.is_demo,
            "workspace_scoped": d.workspace_id is not None, "supersedes": d.supersedes_document_id, "superseded_by": d.superseded_by_document_id,
            "freshness": freshness_status(d.last_checked, bool(d.superseded_by_document_id)), "chunks": chunks,
            "ingested_at": d.created_at.isoformat() if d.created_at else None,
            "update_status": update_status(d.last_checked, d.source.update_frequency_days, bool(d.superseded_by_document_id))}


@router.get("/sources")
def list_sources(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Document.source_id, func.count()).group_by(Document.source_id)).all())
    rows = db.execute(select(Source).order_by(Source.authority_tier, Source.name)).scalars()
    return ok([source_view(s, counts.get(s.id, 0)) for s in rows])


@router.post("/sources", summary="Register a source (admin)")
def create_source(body: SourceIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = Source(**body.model_dump(), last_checked=None)
    db.add(s)
    db.flush()
    audit(db, "source_modified", user_id=user.id, entity_type="source", entity_id=s.id, request=request, change="created")
    return ok(source_view(s))


@router.patch("/sources/{source_id}", summary="Update a source (admin)")
def update_source(source_id: str, body: SourcePatch, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise not_found("Source")
    changes = body.model_dump(exclude_none=True)
    mark = changes.pop("mark_checked", False)
    for k, v in changes.items():
        setattr(s, k, v)
    if mark:
        s.last_checked = datetime.now(timezone.utc)
    audit(db, "source_modified", user_id=user.id, entity_type="source", entity_id=s.id, request=request, changes=sorted(changes) + (["last_checked"] if mark else []))
    return ok(source_view(s))


@router.get("/documents")
def list_documents(domain: Optional[str] = None, jurisdiction: Optional[str] = None, q: Optional[str] = None,
                   ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    stmt = select(Document).where(or_(Document.workspace_id.is_(None), Document.workspace_id == ctx.workspace_id))
    if domain:
        stmt = stmt.where(Document.domain == domain)
    if jurisdiction:
        stmt = stmt.where(Document.jurisdiction == jurisdiction)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q[:100]}%"))
    counts = dict(db.execute(select(DocumentChunk.document_id, func.count()).group_by(DocumentChunk.document_id)).all())
    return ok([doc_view(d, counts.get(d.id, 0)) for d in db.execute(stmt.order_by(Document.domain, Document.title)).scalars()])


@router.get("/documents/{document_id}")
def get_document(document_id: str, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d or (d.workspace_id and d.workspace_id != ctx.workspace_id):
        raise not_found("Document")
    chunks = db.execute(select(DocumentChunk).where(DocumentChunk.document_id == d.id).order_by(DocumentChunk.chunk_index)).scalars().all()
    audit(db, "document_viewed", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="document", entity_id=d.id, request=request)
    return ok({**doc_view(d, len(chunks)), "source_description": d.source.description, "metadata": d.metadata_,
               "chunks": [{"id": c.id, "index": c.chunk_index, "section": c.section, "subsection": c.subsection, "chunk_type": c.chunk_type,
                           "content": c.content, "page_number": c.page_number, "injection_flag": c.injection_flag} for c in chunks]})


def _ingest(request, db, ctx, background: BackgroundTasks, file_name, data, *, meta: dict, source_id: str, workspace_scope: bool):
    try:
        job = create_job(db, filename=file_name, data=data, meta=meta, source_id=source_id,
                         workspace_id=ctx.workspace_id if workspace_scope else None, user_id=ctx.user.id)
    except AppError as exc:
        db.rollback()
        db.add(IngestionJob(workspace_id=ctx.workspace_id, source_id=source_id, file_name=file_name[:300], status="FAILED",
                            error=f"{exc.code}: {exc.message}", created_by=ctx.user.id, finished_at=datetime.now(timezone.utc),
                            steps=[{"step": "failed", "error": exc.code}]))
        audit(db, "document_ingest_failed", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="ingestion", request=request, error=exc.code)
        raise
    audit(db, "document_ingest_queued", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="ingestion", entity_id=job.id,
          request=request, scope="workspace" if workspace_scope else "global")
    background.add_task(process_job, job.id, meta)
    return ok({"job": job_view(job)}, message="Queued. Poll /api/ingestion-jobs/{id} for progress.")


UPLOAD_NOTICE = (
    "Uploaded files are processed on this server, stored only as extracted text in this workspace (not visible to other workspaces), "
    "kept according to the workspace retention policy, and the raw file is deleted after processing. Text may be sent to the configured "
    "LLM provider only as retrieved passages when answering questions. Do not upload unpublished invention details you do not need to."
)


@router.get("/uploads/notice", summary="Privacy & retention notice shown before upload")
def upload_notice(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    from app.models.orm import Workspace
    w = db.get(Workspace, ctx.workspace_id)
    return ok({"notice": UPLOAD_NOTICE, "retention_policy": w.retention_policy, "confidential_mode": w.confidential_mode,
               "max_mb": settings.MAX_UPLOAD_MB, "ocr_available": ocr_available()})


@router.post("/documents", dependencies=[Depends(rate_limit("ingest"))], summary="Upload a document into the workspace (Tier 5, unverified)")
async def upload_document(request: Request, background: BackgroundTasks, file: UploadFile = File(...), title: str = Form(..., min_length=2, max_length=500),
                          jurisdiction: str = Form("INTERNATIONAL"), domain: str = Form("REGULATORY"), document_type: str = Form("USER_UPLOAD"),
                          language: str = Form("en"), privacy_ack: bool = Form(False),
                          ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    ctx.require(WorkspaceRole.RESEARCHER)
    if not privacy_ack:
        raise AppError(428, "PRIVACY_ACK_REQUIRED", UPLOAD_NOTICE)
    src = db.execute(select(Source).where(Source.source_type == "USER_UPLOAD")).scalars().first()
    if not src:
        raise AppError(500, "NO_UPLOAD_SOURCE", "The user-upload source is not configured. Run the seed script.")
    data = await file.read()
    meta = {"title": title, "jurisdiction": jurisdiction, "domain": domain, "document_type": document_type, "language": language}
    return _ingest(request, db, ctx, background, file.filename or "upload", data, meta=meta, source_id=src.id, workspace_scope=True)


@router.post("/documents/ingest", dependencies=[Depends(rate_limit("ingest"))], summary="Ingest an official document into the global corpus (admin)")
async def ingest_document(request: Request, background: BackgroundTasks, file: UploadFile = File(...), title: str = Form(...), source_id: str = Form(...),
                          jurisdiction: str = Form(...), domain: str = Form(...), document_type: str = Form(...), language: str = Form("en"),
                          publication_date: Optional[str] = Form(None), effective_date: Optional[str] = Form(None), url: Optional[str] = Form(None),
                          ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    if ctx.user.role != UserRole.ADMIN:
        raise AppError(403, "FORBIDDEN", "Only administrators can ingest into the global corpus.")
    data = await file.read()
    meta = {"title": title, "jurisdiction": jurisdiction, "domain": domain, "document_type": document_type, "language": language,
            "publication_date": publication_date, "effective_date": effective_date, "url": url}
    return _ingest(request, db, ctx, background, file.filename or "upload", data, meta=meta, source_id=source_id, workspace_scope=False)


@router.get("/ingestion-jobs/{job_id}")
def ingestion_job(job_id: str, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    j = db.get(IngestionJob, job_id)
    if not j or (ctx.user.role != UserRole.ADMIN and j.workspace_id != ctx.workspace_id):
        raise not_found("Ingestion job")
    d = db.get(Document, j.document_id) if j.document_id else None
    return ok({"job": job_view(j), "document": doc_view(d) if d else None})


@router.patch("/documents/{document_id}/review", summary="Curate a document: mark checked, approve, or mark superseded (admin)")
def review_document(document_id: str, body: DocumentReview, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d:
        raise not_found("Document")
    if body.action == "mark_checked":
        d.last_checked = datetime.now(timezone.utc)
    elif body.action == "approve":
        d.review_status = "VERIFIED"
        d.last_checked = datetime.now(timezone.utc)
    elif body.action == "mark_superseded":
        new = db.get(Document, body.superseded_by or "")
        if not new:
            raise AppError(422, "SUPERSEDING_DOCUMENT_REQUIRED", "Give the id of the document that supersedes this one.")
        d.superseded_by_document_id = new.id
        new.supersedes_document_id = d.id
    if body.version:
        d.version = body.version
    if body.effective_date:
        d.effective_date = body.effective_date
    audit(db, "source_modified", user_id=user.id, entity_type="document", entity_id=d.id, request=request, review_action=body.action, note=body.note)
    return ok(doc_view(d))


@router.get("/coverage", summary="Jurisdiction × domain coverage matrix computed from the ingested corpus")
def coverage_matrix(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    return ok(coverage(db))


@router.get("/admin/update-queue", summary="Documents due for re-checking, by source update frequency")
def admin_update_queue(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return ok(update_queue(db))


@router.get("/privacy", summary="Where data is stored and sent, retention, and LLM provider data handling")
def privacy(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    from app.models.orm import Workspace
    w = db.get(Workspace, ctx.workspace_id)
    return ok({
        "storage": "PostgreSQL (this deployment). Innovation profiles, conversations, evidence and extracted upload text are stored per workspace; "
                   "other workspaces cannot read them. Raw uploaded files are deleted after processing.",
        "encryption": "Transport: HTTPS when deployed behind TLS (the public tunnel is HTTPS). At rest: relies on disk/volume encryption of the "
                      "database host (enable FileVault/LUKS or managed-DB encryption in production); passwords are bcrypt-hashed; IPs are stored "
                      "only as salted hashes.",
        "retention": {"policy": w.retention_policy, "applies_to": "conversations and workspace uploads (audit logs are kept)",
                      "enforcement": "Admin → System Health → Run retention purge (or `python -m app.seed.retention`)."},
        "llm": data_handling(),
        "access_control": "Authentication required; per-workspace roles (Owner/Admin/Researcher/Reviewer/Viewer); admin-only corpus changes.",
        "sensitive_input": "Confidential innovations require an explicit acknowledgement; a warning is shown before submission and uploads.",
        "upload_notice": UPLOAD_NOTICE,
    })


def job_view(j: IngestionJob) -> dict:
    return {"id": j.id, "file_name": j.file_name, "status": j.status, "steps": j.steps, "error": j.error, "document_id": j.document_id,
            "created_at": j.created_at.isoformat(), "finished_at": j.finished_at.isoformat() if j.finished_at else None}


@router.get("/ingestion-jobs")
def ingestion_jobs(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    q = select(IngestionJob)
    if ctx.user.role != UserRole.ADMIN:
        q = q.where(IngestionJob.workspace_id == ctx.workspace_id)
    return ok([job_view(j) for j in db.execute(q.order_by(IngestionJob.created_at.desc()).limit(100)).scalars()])
