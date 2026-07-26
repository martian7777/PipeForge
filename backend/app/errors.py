"""Global exception handling.

Nothing reaches the client as an unstyled stack trace. Every error -- expected or not --
comes back as the same JSON envelope::

    {
      "detail": "Human readable message",          # kept for existing clients
      "error": {
        "type": "validation_error",
        "message": "Human readable message",
        "request_id": "3f2c...",                   # cross-reference with the logs
        "details": [ ... ]                          # optional, per-field for 422
      }
    }

Unhandled exceptions log the full traceback server-side but return only a generic
message plus the request id, so internal detail never leaks to the caller.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging_config import get_logger, request_id_ctx

logger = get_logger(__name__)

# Machine-readable ``error.type`` for the statuses we raise deliberately.
_TYPE_BY_STATUS = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def _request_id(request: Request | None) -> str | None:
    """Resolve the correlation id.

    ``request.state`` is checked first and the context variable second, because the
    catch-all ``Exception`` handler runs in Starlette's ServerErrorMiddleware -- which
    sits *outside* RequestContextMiddleware, so by then the context variable has already
    been reset. The value stashed on the request survives.
    """
    if request is not None:
        stashed = getattr(request.state, "request_id", None)
        if stashed:
            return str(stashed)
    return request_id_ctx.get()


def error_response(
    request: Request | None,
    status_code: int,
    message: str,
    *,
    error_type: str | None = None,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body: dict[str, Any] = {
        "detail": message,
        "error": {
            "type": error_type or _TYPE_BY_STATUS.get(status_code, "error"),
            "message": message,
            "request_id": request_id,
        },
    }
    if details is not None:
        body["error"]["details"] = details

    # Echo the id even when the response bypasses RequestContextMiddleware, so a user
    # reporting an error can always quote something that appears in the logs.
    final_headers = dict(headers or {})
    if request_id:
        final_headers.setdefault("X-Request-ID", request_id)

    # The catch-all handler runs outside SecurityHeadersMiddleware, so error responses
    # would otherwise ship bare. Set the ones that matter for a JSON body here.
    final_headers.setdefault("X-Content-Type-Options", "nosniff")
    final_headers.setdefault("X-Frame-Options", "DENY")
    final_headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")

    return JSONResponse(status_code=status_code, content=body, headers=final_headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Deliberate ``HTTPException``s -- pass the message through, keep the envelope."""
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    details = None if isinstance(exc.detail, str) else exc.detail
    if exc.status_code >= 500:
        logger.error(
            "server error raised",
            extra={"event": "http.error", "status_code": exc.status_code, "path": request.url.path},
        )
    return error_response(
        request,
        exc.status_code,
        detail,
        details=details,
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 with a compact per-field breakdown instead of FastAPI's raw error list."""
    details = [
        {
            "field": ".".join(str(p) for p in err.get("loc", ()) if p != "body"),
            "message": err.get("msg", "invalid value"),
            "type": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    logger.info(
        "request validation failed",
        extra={"event": "http.validation_failed", "path": request.url.path, "fields": details},
    )
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Request validation failed",
        details=details,
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 in the standard envelope, with Retry-After so clients can back off."""
    logger.warning(
        "rate limit exceeded",
        extra={
            "event": "http.rate_limited",
            "path": request.url.path,
            "limit": str(exc.detail),
        },
    )
    return error_response(
        request,
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Rate limit exceeded: {exc.detail}. Please retry shortly.",
        headers={"Retry-After": "60"},
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """A unique/foreign-key violation is the caller's problem (409), not a 500."""
    logger.warning(
        "database integrity error",
        extra={"event": "db.integrity_error", "path": request.url.path},
        exc_info=exc,
    )
    return error_response(
        request,
        status.HTTP_409_CONFLICT,
        "The request conflicts with existing data.",
    )


async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception(
        "database error",
        extra={"event": "db.error", "path": request.url.path, "method": request.method},
    )
    return error_response(
        request,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "A database error occurred. Please retry.",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The catch-all. Full traceback to the logs, opaque message to the client."""
    logger.exception(
        "unhandled exception",
        extra={
            "event": "http.unhandled_exception",
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
        },
    )
    return error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An internal error occurred. Quote the request_id when reporting this.",
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Register every handler. Order is irrelevant -- FastAPI dispatches by type."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
