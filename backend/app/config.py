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

    model_config = SettingsConfigDict(env_prefix="PIPEFORGE_", env_file=".env", extra="ignore")

    app_name: str = "PipeForge"

    # Database. Defaults to local SQLite; set PIPEFORGE_DATABASE_URL to a Postgres DSN
    # (e.g. postgresql+psycopg://user:pass@host/db) for multi-replica / horizontal scaling.
    database_url: str = f"sqlite:///{(STORAGE_DIR / 'pipeforge.db').as_posix()}"

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

    # CORS origins for the local Vite dev server (override via PIPEFORGE_CORS_ORIGINS).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Max upload size in bytes (200 MB default).
    max_upload_bytes: int = 200 * 1024 * 1024

    # Number of preview rows returned by the preview endpoint.
    preview_rows: int = 50

    # Background training job runner: number of concurrent pipeline jobs.
    job_max_workers: int = 2

    # --- Security / auth ---
    # JWT signing secret. MUST be overridden in production via PIPEFORGE_JWT_SECRET.
    jwt_secret: str = "dev-insecure-change-me-please-override-in-production-32b+"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24  # 24h

    # --- Rate limiting ---
    # slowapi limit strings. Storage backend: in-memory by default; set a Redis URI
    # (e.g. redis://localhost:6379) via PIPEFORGE_RATELIMIT_STORAGE for multi-replica use.
    ratelimit_default: str = "200/minute"
    ratelimit_auth: str = "10/minute"
    ratelimit_upload: str = "30/minute"
    ratelimit_agent: str = "60/minute"
    ratelimit_storage: str = "memory://"

    # --- Agentic AI layer (pluggable / bring-your-own provider) ---
    # Default provider for the agent layer. "off" disables agents entirely (the classic,
    # deterministic pipeline is unaffected). Any provider in agents/providers.PROVIDERS
    # works — anthropic | openai | google | ollama | openai_compatible. Per-agent provider
    # + model overrides live in the AgentConfig table (edited from the settings UI); these
    # are the system defaults.
    llm_provider: str = "off"
    # Generic secret used for the active provider. Never sent to the frontend.
    llm_api_key: str = ""
    # Optional per-provider keys — set these to mix providers across agents. Each falls
    # back to llm_api_key when blank. (PIPEFORGE_ANTHROPIC_API_KEY, PIPEFORGE_OPENAI_API_KEY,
    # PIPEFORGE_GOOGLE_API_KEY.)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    # Base URL for OpenAI-compatible endpoints (Ollama, vLLM, LM Studio, proxies, or any
    # OpenAI-compatible gateway). Blank = provider default.
    llm_base_url: str = ""
    # System-default models per role. Recommended Anthropic Claude tiers.
    llm_model_orchestrator: str = "claude-opus-4-8"
    llm_model_analyst: str = "claude-opus-4-8"
    llm_model_cheap: str = "claude-haiku-4-5"
    llm_model_chat: str = "claude-sonnet-5"
    # Cost guardrails.
    agent_max_steps: int = 12
    agent_default_mode: str = "advise"  # off | advise | chat | copilot | autopilot

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
