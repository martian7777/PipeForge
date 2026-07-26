"""PipeForge FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000
from the ``backend`` directory. Behind a proxy add ``--proxy-headers`` so client IPs
(and therefore rate-limit buckets and audit records) reflect the real caller.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import oauth
from .api import admin, agents, auth, datasets, runs
from .config import settings
from .db import SessionLocal, engine, init_db
from .errors import install_exception_handlers
from .logging_config import configure_logging, get_logger
from .middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from .ratelimit import limiter
from .security import purge_expired_refresh_tokens

configure_logging()
logger = get_logger(__name__)

_INSECURE_JWT_SECRET = "dev-insecure-change-me-please-override-in-production-32b+"


def _startup_security_audit() -> None:
    """Shout about configuration that is fine locally but dangerous in production."""
    if settings.jwt_secret == _INSECURE_JWT_SECRET:
        logger.warning(
            "PIPEFORGE_JWT_SECRET is the built-in development default -- override it "
            "before exposing this deployment",
            extra={"event": "startup.insecure_config", "setting": "jwt_secret"},
        )
    if len(settings.jwt_secret) < 32:
        logger.warning(
            "PIPEFORGE_JWT_SECRET is shorter than 32 bytes",
            extra={"event": "startup.insecure_config", "setting": "jwt_secret"},
        )
    if settings.ratelimit_storage.startswith("memory://"):
        logger.warning(
            "rate limits are stored in-process; set PIPEFORGE_RATELIMIT_STORAGE to a "
            "Redis URI so limits hold across replicas",
            extra={"event": "startup.insecure_config", "setting": "ratelimit_storage"},
        )
    if not settings.refresh_cookie_secure:
        logger.warning(
            "refresh cookie is not marked Secure; set PIPEFORGE_REFRESH_COOKIE_SECURE=true "
            "when serving over TLS",
            extra={"event": "startup.insecure_config", "setting": "refresh_cookie_secure"},
        )
    if "*" in settings.cors_origins:
        logger.warning(
            "CORS allows any origin while credentials are enabled",
            extra={"event": "startup.insecure_config", "setting": "cors_origins"},
        )

    enabled = [p["name"] for p in oauth.available_providers()]
    logger.info(
        "sso providers configured",
        extra={"event": "startup.sso", "providers": enabled or ["none"]},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _startup_security_audit()

    # Housekeeping: drop refresh tokens that expired long ago.
    with SessionLocal() as db:
        purged = purge_expired_refresh_tokens(db)
    logger.info(
        "application started",
        extra={"event": "startup.complete", "purged_refresh_tokens": purged},
    )
    yield
    logger.info("application shutting down", extra={"event": "shutdown"})


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    lifespan=lifespan,
    # OpenAPI is useful but not something to publish unauthenticated in production;
    # gate it at the ingress if the deployment is internet-facing.
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# --- Exception handling ---
# Registered first so nothing can escape as an unstyled stack trace.
install_exception_handlers(app)

# --- Rate limiting ---
# The 429 response shape comes from errors.rate_limit_handler, not slowapi's default.
app.state.limiter = limiter

# --- Middleware ---
# Starlette runs the LAST added middleware outermost, so request-id binding wraps
# everything below it and every log line inside the request carries the correlation id.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,  # required for the HttpOnly refresh cookie
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.refresh_cookie_secure)
app.add_middleware(RequestContextMiddleware)

# --- Routes ---
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(datasets.router)
app.include_router(runs.router)
app.include_router(agents.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness: the process is up. Deliberately does not touch the database."""
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/health/ready", tags=["health"])
def readiness(response: Response) -> dict[str, str]:
    """Readiness: dependencies reachable. Point the load balancer here.

    Returns 503 when the database is unreachable so the balancer drains this replica
    instead of routing traffic it cannot serve.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness check failed", extra={"event": "health.not_ready"})
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ready", "database": "ok"}
