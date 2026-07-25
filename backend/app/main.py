"""PipeForge FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000
from the ``backend`` directory.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .api import agents, auth, datasets, runs
from .config import settings
from .db import init_db
from .ratelimit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create storage dirs and database tables on startup.
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

# --- Rate limiting ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    """Attach conservative security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(runs.router)
app.include_router(agents.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
