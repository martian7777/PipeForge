"""Application configuration and filesystem paths.

Local-first: everything lives under ``backend/storage``. No external services.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BACKEND_DIR / "storage"


class Settings(BaseSettings):
    """Runtime settings. Override via environment variables or a .env file."""

    model_config = SettingsConfigDict(env_prefix="AUTODS_", env_file=".env", extra="ignore")

    app_name: str = "AutoDS"

    # Database. Defaults to local SQLite; set AUTODS_DATABASE_URL to a Postgres DSN
    # (e.g. postgresql+psycopg://user:pass@host/db) for multi-replica / horizontal scaling.
    database_url: str = f"sqlite:///{(STORAGE_DIR / 'autods.db').as_posix()}"

    # Storage subdirectories.
    storage_dir: Path = STORAGE_DIR
    uploads_dir: Path = STORAGE_DIR / "uploads"
    artifacts_dir: Path = STORAGE_DIR / "artifacts"
    reports_dir: Path = STORAGE_DIR / "reports"
    samples_dir: Path = STORAGE_DIR / "samples"

    # File-storage sharding: uploaded files are placed under NN/ subdirectories keyed
    # by a hash prefix, so no single directory holds millions of files. Set the number
    # of hex characters used for the shard prefix (2 => 256 shards).
    storage_shard_prefix_len: int = 2

    # CORS origins for the local Vite dev server (override via AUTODS_CORS_ORIGINS).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Max upload size in bytes (200 MB default).
    max_upload_bytes: int = 200 * 1024 * 1024

    # Number of preview rows returned by the preview endpoint.
    preview_rows: int = 50

    # Background training job runner: number of concurrent pipeline jobs.
    job_max_workers: int = 2

    # --- Security / auth ---
    # JWT signing secret. MUST be overridden in production via AUTODS_JWT_SECRET.
    jwt_secret: str = "dev-insecure-change-me-please-override-in-production-32b+"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24  # 24h

    # --- Rate limiting ---
    # slowapi limit strings. Storage backend: in-memory by default; set a Redis URI
    # (e.g. redis://localhost:6379) via AUTODS_RATELIMIT_STORAGE for multi-replica use.
    ratelimit_default: str = "200/minute"
    ratelimit_auth: str = "10/minute"
    ratelimit_upload: str = "30/minute"
    ratelimit_storage: str = "memory://"

    def ensure_dirs(self) -> None:
        """Create all storage directories if they do not exist."""
        for d in (
            self.storage_dir,
            self.uploads_dir,
            self.artifacts_dir,
            self.reports_dir,
            self.samples_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
