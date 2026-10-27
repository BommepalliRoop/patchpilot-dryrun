"""Error envelope and global exception handlers (RISKS E1, E2).

Every error response is `{ "error": { "code", "message" } }`. Messages never contain stack traces or secrets.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("patchpilot.api")

_STATUS_CODES = {400: "invalid_request", 401: "unauthorized", 404: "not_found", 409: "conflict",
                 429: "rate_limited", 500: "internal_error"}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    from app.core.security import redact  # local import: security imports this module

    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": redact(message)}})


def _field_names(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header"))
        parts.append(f"{loc or 'request'}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid request"


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(400, "invalid_request", _field_names(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "invalid_request")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Full trace goes to the server log (redacted by the log filter); the client sees nothing internal.
        logger.error("unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(500, "internal_error", "Internal server error")
