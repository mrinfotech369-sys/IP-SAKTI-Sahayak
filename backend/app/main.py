"""Main FastAPI application for IP-SAKTI Sahayak."""
import json
import logging
import time
import uuid

from dotenv import load_dotenv

from app.core.config import REPO_ROOT, settings, validate_settings

# Provider factories in rag/ read os.environ; make .env visible to them.
load_dotenv(REPO_ROOT / ".env", override=False)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.api.endpoints import (  # noqa: E402
    admin,
    auth,
    chat,
    corpus,
    evaluations,
    health,
    innovations,
    review,
    search,
    workspaces,
)
from app.core.responses import install_error_handlers, ok  # noqa: E402


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"level": record.levelname, "logger": record.name, "msg": record.getMessage(), "ts": int(record.created * 1000)}
        for k in ("request_id", "user_id", "workspace_id", "endpoint", "status", "latency_ms"):
            if hasattr(record, k):
                base[k] = getattr(record, k)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=settings.LOG_LEVEL, handlers=[_handler], force=True)
log = logging.getLogger("ipsakti.http")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        settings.PROJECT_DESCRIPTION
        + "\n\n**Auth:** send `Authorization: Bearer <token>` (from `/api/auth/login`) or use the httpOnly session cookie. "
        "Cookie-authenticated writes must include `X-Requested-With: ipsakti`. Select a workspace with `X-Workspace-Id`.\n\n"
        "**Responses:** `{success, data, meta}` or `{success: false, error: {code, message}}`."
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in settings.CORS_ORIGINS if o != "*"] + [settings.APP_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Workspace-Id"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    started = time.monotonic()
    response = await call_next(request)
    latency = int((time.monotonic() - started) * 1000)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    # Never log bodies: innovation text may be confidential.
    log.info(
        "request",
        extra={
            "request_id": request_id,
            "user_id": getattr(request.state, "user_id", None),
            "workspace_id": getattr(request.state, "workspace_id", None),
            "endpoint": f"{request.method} {request.url.path}",
            "status": response.status_code,
            "latency_ms": latency,
        },
    )
    return response


install_error_handlers(app)

for r in (auth, workspaces, innovations, chat, search, review, corpus, admin, evaluations):
    app.include_router(r.router, prefix=settings.API_PREFIX)
app.include_router(health.router)
app.include_router(health.router, prefix=settings.API_PREFIX, include_in_schema=False)


@app.on_event("startup")
def _startup() -> None:
    for w in validate_settings():
        logging.getLogger("ipsakti.config").warning(w)


@app.get("/", tags=["Root"])
def root():
    return ok({"message": "IP-SAKTI Sahayak API", "docs": "/docs", "health": "/health"})
