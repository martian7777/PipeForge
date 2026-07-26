"""HTTP middleware: request correlation, access logging, and security headers."""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from .logging_config import get_logger, request_id_ctx, user_id_ctx

logger = get_logger("access")

# Health checks are polled constantly by the load balancer; logging each is noise.
_QUIET_PATHS = frozenset({"/api/health", "/api/health/ready"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign every request an id, bind it to the logging context, and log the outcome.

    The id is taken from an inbound ``X-Request-ID`` when the gateway supplies one
    (so a trace spans the whole hop chain) and echoed back on the response, which is
    what makes a client-reported error id findable in the logs.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(self.header_name) or uuid.uuid4().hex
        request_id_token = request_id_ctx.set(request_id)
        user_id_token = user_id_ctx.set(None)
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers build the response; we only record the timing and
            # re-raise so they still run.
            logger.exception(
                "request failed",
                extra={
                    "event": "http.request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        finally:
            request_id_ctx.reset(request_id_token)
            user_id_ctx.reset(user_id_token)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[self.header_name] = request_id

        if request.url.path not in _QUIET_PATHS:
            level = logger.warning if response.status_code >= 400 else logger.info
            level(
                f"{request.method} {request.url.path} {response.status_code}",
                extra={
                    "event": "http.request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response.

    ``setdefault`` semantics: a route that deliberately sets its own value (an embedded
    HTML report, say) keeps it.
    """

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        # The API serves JSON and file downloads, for which a deny-all CSP is right.
        # The generated EDA report is self-contained HTML with inline scripts/styles,
        # so it gets a policy that permits those but still blocks network egress.
        if response.media_type == "text/html" or headers.get("content-type", "").startswith(
            "text/html"
        ):
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' data: blob:; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "connect-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        else:
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        if self.hsts:
            headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
