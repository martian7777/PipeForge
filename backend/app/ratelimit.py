"""Rate limiting via slowapi.

Uses the client IP as the key by default. The storage backend is configurable:
in-memory for single-process dev, or Redis (``PIPEFORGE_RATELIMIT_STORAGE=redis://...``)
so limits are shared across replicas behind a load balancer.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.ratelimit_default],
    storage_uri=settings.ratelimit_storage,
)
