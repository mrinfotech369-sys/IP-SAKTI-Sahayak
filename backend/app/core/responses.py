"""Standard response envelope and error handling.

Success: {"success": true, "data": ..., "meta": {...}}
Error:   {"success": false, "error": {"code": "...", "message": "..."}}
"""
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("ipsakti")


def ok(data: Any = None, **meta: Any) -> dict:
    return {"success": True, "data": data, "meta": meta}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Optional[dict] = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def not_found(entity: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{entity} was not found or you do not have access to it.")


def forbidden(message: str = "You do not have permission to perform this action.") -> AppError:
    return AppError(403, "FORBIDDEN", message)


def _error(status: int, code: str, message: str, details: Optional[dict] = None) -> JSONResponse:
    body: dict = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    429: "RATE_LIMITED",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return _error(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
            fields.append({"field": loc, "message": err.get("msg", "Invalid value")})
        first = fields[0] if fields else {"field": "", "message": "Invalid input"}
        msg = f"Invalid input for '{first['field']}': {first['message']}" if first["field"] else first["message"]
        return _error(422, "VALIDATION_ERROR", msg, {"fields": fields})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled error request_id=%s path=%s", request_id, request.url.path)
        return _error(
            500,
            "INTERNAL_ERROR",
            "The server hit an unexpected error while processing this request. "
            f"It has been logged (reference {request_id}). Please retry; if it persists, contact an administrator.",
        )
