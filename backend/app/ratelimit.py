"""Rate limiting via slowapi.

The limit key is the **authenticated user** when the request carries a valid access
token, and the client IP otherwise. Keying on identity is what stops an authenticated
attacker from bypassing limits by rotating source addresses, while unauthenticated
traffic (login, register) still gets per-IP protection.

Behind the nginx gateway, ``X-Forwarded-For`` carries the real client address; uvicorn
runs with ``--proxy-headers`` so ``get_remote_address`` sees it rather than the proxy.

The storage backend is configurable: in-memory for single-process dev, or Redis
(``PIPEFORGE_RATELIMIT_STORAGE=redis://...``) so limits are shared across replicas
behind a load balancer.
"""
from __future__ import annotations

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .config import settings


def identity_key(request: Request) -> str:
    """``user:<id>`` for authenticated callers, ``ip:<addr>`` otherwise.

    Decoding here is deliberately cheap and signature-only -- no database hit. A forged
    token cannot pass signature verification, so the key cannot be spoofed; an expired
    or malformed one simply falls back to the IP bucket.
    """
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else None

    if token:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            if payload.get("typ") == "access" and payload.get("sub"):
                return f"user:{payload['sub']}"
        except jwt.PyJWTError:
            pass  # fall through to the IP bucket

    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=identity_key,
    default_limits=[settings.ratelimit_default],
    storage_uri=settings.ratelimit_storage,
    headers_enabled=True,  # emit X-RateLimit-Limit/Remaining/Reset so clients can back off
)
