from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.responses import ok
from app.db import check_database, engine
from app.services.embeddings import get_embedder
from app.services.llm import llm_health

router = APIRouter(prefix="/health", tags=["Health"])


def _db():
    try:
        return check_database()
    except Exception as exc:
        return {"database": "error", "detail": f"Database unreachable ({type(exc).__name__}). Is Postgres running (docker compose up -d postgres)?"}


def _vector():
    try:
        with engine.connect() as c:
            n = c.execute(text("SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL")).scalar()
        return {"vector": "ok", "indexed_chunks": n, "embedding_provider": get_embedder().name, "dimension": settings.EMBEDDING_DIMENSION}
    except Exception as exc:
        return {"vector": "error", "detail": type(exc).__name__}


@router.get("")
def health():
    db, vec = _db(), _vector()
    status = "ok" if db.get("database") == "ok" and vec.get("vector") == "ok" else "degraded"
    return ok({"status": status, "service": settings.PROJECT_NAME, "version": settings.VERSION, "environment": settings.APP_ENV,
               "llm_provider": settings.LLM_PROVIDER, **db, **vec})


@router.get("/database")
def health_db():
    return ok(_db())


@router.get("/vector")
def health_vector():
    return ok(_vector())


@router.get("/llm")
def health_llm():
    return ok(llm_health())
