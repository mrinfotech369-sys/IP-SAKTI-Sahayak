"""Document ingestion: validate → hash → metadata → detect format → extract (OCR fallback) →
section detection → clean → structure-aware chunk → injection scan → embed → FTS index
(generated column) → validated corpus.

Uploads are untrusted: size/type/signature checks, no execution, text treated as data.
Processing runs as a background job so heavy parsing/OCR never blocks a web request.
The raw uploaded file is deleted once processing finishes (only extracted text is kept,
subject to the workspace retention policy).
"""
import hashlib
import html
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.responses import AppError
from app.db import SessionLocal
from app.models.orm import Document, DocumentChunk, IngestionJob, Source
from app.services.embeddings import get_embedder
from app.services.query_understanding import detect_injection
from ingestion.chunker import chunk_pages
from ingestion.parsers.pdf_parser import PageResult, parse_pdf

log = logging.getLogger("ipsakti.ingestion")

ALLOWED = {".pdf": b"%PDF", ".txt": None, ".md": None}
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TAGS = re.compile(r"<[^>]{0,200}>")
STAGING = Path(settings.STORAGE_BUCKET) / "staging"


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _chunk_type(text: str, section: Optional[str]) -> str:
    s = (section or "").lower()
    t = text.lower()[:200]
    if re.match(r"^\s*\d+\.\s+(an?|the)\s", text) or "claim" in s:
        return "CLAIM"
    for k in ("abstract", "methods", "results", "limitations", "conclusion"):
        if s.startswith(k):
            return k.upper()
    if " means " in t or "includes" in t[:120] or "definition" in s:
        return "DEFINITION"
    if re.search(r"\b(shall|must|required)\b", t):
        return "REQUIREMENT"
    return "PARAGRAPH"


def sanitize(text: str) -> str:
    text = CONTROL.sub(" ", text)
    text = TAGS.sub(" ", html.unescape(text))
    return re.sub(r"[ \t]+", " ", text).strip()


def validate_upload(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", f"File type '{ext or 'unknown'}' is not allowed. Upload PDF, TXT or MD.")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError(413, "FILE_TOO_LARGE", f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.")
    if not data:
        raise AppError(400, "EMPTY_FILE", "The uploaded file is empty.")
    magic = ALLOWED[ext]
    if magic and not data.startswith(magic):
        raise AppError(415, "FILE_SIGNATURE_MISMATCH", "File content does not match its extension (possible disguised file).")
    if ext in (".txt", ".md"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise AppError(415, "INVALID_TEXT_ENCODING", "Text files must be UTF-8 encoded.")
    if ext == ".pdf" and (b"/JavaScript" in data or b"/Launch" in data):
        raise AppError(415, "UNSAFE_PDF", "PDF contains embedded JavaScript or launch actions and was rejected.")
    return ext


def _ocr_pages(path: Path, page_nums: list[int]) -> tuple[dict[int, str], Optional[float]]:
    """OCR the given 1-indexed pages with Tesseract. Returns texts and mean word confidence (0–100)."""
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    texts, confs = {}, []
    with fitz.open(path) as doc:
        for n in page_nums[:50]:
            pix = doc[n - 1].get_pixmap(dpi=200)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
            words = [(w, float(c)) for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
            texts[n] = " ".join(w for w, _ in words)
            confs += [c for _, c in words]
    return texts, (round(sum(confs) / len(confs), 1) if confs else None)


def create_job(
    db: Session, *, filename: str, data: bytes, meta: dict, source_id: str, workspace_id: Optional[str], user_id: str,
) -> IngestionJob:
    """Validate synchronously (fast), stage the file and create a PENDING job."""
    source = db.get(Source, source_id)
    if not source:
        raise AppError(404, "SOURCE_NOT_FOUND", "Select a registered source for this document.")
    ext = validate_upload(filename, data)
    digest = hashlib.sha256(data).hexdigest()
    dup = db.execute(select(Document).where(Document.content_hash == digest, Document.workspace_id == workspace_id)).scalar_one_or_none()
    if dup:
        raise AppError(409, "DUPLICATE_DOCUMENT", f"This file was already ingested as '{dup.title}'.")
    job = IngestionJob(workspace_id=workspace_id, source_id=source_id, file_name=filename[:300], status="PENDING", created_by=user_id,
                       steps=[{"step": "validate", "at": datetime.now(timezone.utc).isoformat(), "file_type": ext, "bytes": len(data)},
                              {"step": "hash", "sha256": digest[:16]}])
    db.add(job)
    db.flush()
    STAGING.mkdir(parents=True, exist_ok=True)
    (STAGING / f"{job.id}{ext}").write_bytes(data)
    job.steps = [*job.steps, {"step": "queued", "meta": {k: v for k, v in meta.items() if v}}]
    return job


def process_job(job_id: str, meta: dict) -> None:
    """Background task: runs in its own DB session."""
    db = SessionLocal()
    job = db.get(IngestionJob, job_id)
    path = next(STAGING.glob(f"{job_id}.*"), None)

    def step(name: str, **info):
        job.steps = [*job.steps, {"step": name, "at": datetime.now(timezone.utc).isoformat(), **info}]
        db.commit()

    try:
        job.status = "RUNNING"
        db.commit()
        if path is None:
            raise AppError(410, "STAGED_FILE_MISSING", "The uploaded file is no longer available; upload it again.")
        data = path.read_bytes()
        ext = path.suffix
        source = db.get(Source, job.source_id)
        ocr_conf = None
        if ext == ".pdf":
            parsed = parse_pdf(str(path), max_pages=300)
            pages, method = parsed.pages, "PYMUPDF"
            step("extract", pages=len(pages), method=method, ocr_needed_pages=parsed.ocr_pages[:20])
            if parsed.ocr_pages:
                if ocr_available():
                    texts, ocr_conf = _ocr_pages(path, parsed.ocr_pages)
                    for p in pages:
                        if p.page_num in texts:
                            p.text = texts[p.page_num]
                    method = "PYMUPDF+TESSERACT_OCR"
                    step("ocr", pages=len(texts), mean_confidence=ocr_conf,
                         validation="Low-confidence OCR (<70) is flagged for human validation." if ocr_conf is not None and ocr_conf < 70 else "OK")
                else:
                    step("ocr", skipped=True, reason="Tesseract not installed on this server")
        else:
            pages, method = [PageResult(page_num=1, text=data.decode("utf-8"))], "PLAINTEXT"
            step("extract", pages=1, method=method)
        for p in pages:
            p.text = sanitize(p.text)
        if not any(p.text for p in pages):
            raise AppError(422, "NO_EXTRACTABLE_TEXT", "No text could be extracted (scanned PDF without OCR, or empty document).")
        step("clean")

        chunks = chunk_pages(pages, target_tokens=350, overlap_tokens=40, min_tokens=10)
        if not chunks:
            # Very short documents fall under the chunker's minimum; keep one chunk per page.
            from ingestion.chunker import Chunk, estimate_tokens
            chunks = [Chunk(chunk_index=i, text=p.text, token_count=estimate_tokens(p.text), page_number=p.page_num, section=None, heading=None)
                      for i, p in enumerate([p for p in pages if p.text])]
        if not chunks:
            raise AppError(422, "NO_INDEXABLE_TEXT", "The document produced no indexable passages.")
        step("chunk", chunks=len(chunks), strategy="section-aware paragraphs (Section/Rule/Article headings preserved)")

        is_official = source.authority_tier <= 2
        review = "PENDING_REVIEW" if not is_official else "UPLOADED_OFFICIAL"
        if ocr_conf is not None and ocr_conf < 70:
            review = "PENDING_REVIEW"
        doc = Document(
            source_id=source.id, workspace_id=job.workspace_id, title=meta["title"][:500], document_type=meta["document_type"], domain=meta["domain"],
            jurisdiction=meta["jurisdiction"], publication_date=meta.get("publication_date"), effective_date=meta.get("effective_date"),
            last_checked=datetime.now(timezone.utc), version="Uploaded", language=meta.get("language") or "en", url=meta.get("url"),
            access_level="WORKSPACE" if job.workspace_id else "PUBLIC", content_hash=hashlib.sha256(data).hexdigest(), extraction_method=method,
            ocr_confidence=ocr_conf, review_status=review, is_demo=False, metadata_={"file_name": job.file_name, "uploaded_by": job.created_by},
        )
        db.add(doc)
        db.flush()
        emb = get_embedder()
        vectors = emb.embed_batch([c.text for c in chunks]) if chunks else []
        flagged = 0
        for c, v in zip(chunks, vectors):
            inj = detect_injection(c.text)
            flagged += inj
            sec = c.section or c.heading
            db.add(DocumentChunk(document_id=doc.id, chunk_index=c.chunk_index, section=sec[:300] if sec else None, subsection=None,
                                 chunk_type=_chunk_type(c.text, sec), content=c.text, page_number=c.page_number,
                                 metadata_={"token_count": c.token_count}, injection_flag=inj, embedding=v))
        job.document_id = doc.id
        job.status = "SUCCEEDED"
        job.finished_at = datetime.now(timezone.utc)
        step("embed_and_index", embedding_provider=emb.name, injection_flagged_chunks=flagged)
        step("validated_corpus", review_status=doc.review_status)
    except AppError as exc:
        db.rollback()
        job = db.get(IngestionJob, job_id)
        job.status, job.error, job.finished_at = "FAILED", f"{exc.code}: {exc.message}", datetime.now(timezone.utc)
        job.steps = [*job.steps, {"step": "failed", "error": exc.code}]
        db.commit()
    except Exception as exc:  # parser crash on malformed input
        log.exception("ingestion job %s failed", job_id)
        db.rollback()
        job = db.get(IngestionJob, job_id)
        job.status, job.error, job.finished_at = "FAILED", f"PARSE_ERROR: {type(exc).__name__}", datetime.now(timezone.utc)
        job.steps = [*job.steps, {"step": "failed", "error": "PARSE_ERROR"}]
        db.commit()
    finally:
        if path and path.exists():
            path.unlink()  # raw upload is not retained
        db.close()
