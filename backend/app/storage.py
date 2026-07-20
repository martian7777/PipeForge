"""Sharded local file storage.

Uploaded files are distributed across ``NN/`` subdirectories keyed by a hash prefix
so that no single directory accumulates an unbounded number of files. This is the
local-filesystem analogue of object-store key sharding and keeps directory listings
fast at scale. The scheme is deterministic, so a stored path can always be recomputed
from its key.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from .config import settings


def new_object_key(filename: str) -> str:
    """Generate a unique, collision-resistant storage key preserving the extension."""
    suffix = Path(filename).suffix.lower()
    return f"{uuid.uuid4().hex}{suffix}"


def shard_for(key: str) -> str:
    """Return the shard subdirectory name for a key (stable hash prefix)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest[: settings.storage_shard_prefix_len]


def upload_path(key: str, create: bool = True) -> Path:
    """Resolve the absolute path for an upload key, creating the shard dir if needed."""
    shard = shard_for(key)
    directory = settings.uploads_dir / shard
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory / key


def artifact_path(key: str, create: bool = True) -> Path:
    """Resolve the absolute path for a model artifact key."""
    shard = shard_for(key)
    directory = settings.artifacts_dir / shard
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory / key
