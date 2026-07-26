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
    # Access tokens are short-lived; clients silently renew with a refresh token.
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    # Refresh tokens are delivered as an HttpOnly cookie so browser JS never sees them.
    refresh_cookie_name: str = "pipeforge_refresh"
    refresh_cookie_secure: bool = False  # set True behind TLS in production
    refresh_cookie_samesite: str = "lax"  # lax | strict | none
    # Bootstrap: this email is promoted to admin on registration/first SSO login.
    # If blank, the very first user to register becomes the admin.
    bootstrap_admin_email: str = ""

    # --- OAuth 2.0 / OIDC single sign-on ---
    # Public base URL of the API as the browser sees it; used to build the redirect_uri
    # registered with each provider (``{base}/api/auth/oauth/{provider}/callback``).
    public_base_url: str = "http://localhost:5173"
    # Where the browser lands after the callback completes (SPA route).
    oauth_post_login_path: str = "/auth/callback"
    # Providers are enabled purely by supplying a client id + secret.
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"
    # Restrict SSO sign-up to these email domains (empty = allow any).
    oauth_allowed_email_domains: list[str] = []
    # Lifetime of the signed state/PKCE cookie that spans the authorize->callback hop.
    oauth_state_ttl_seconds: int = 600

    # --- Rate limiting ---
    # slowapi limit strings. Storage backend: in-memory by default; set a Redis URI
    # (e.g. redis://localhost:6379) via PIPEFORGE_RATELIMIT_STORAGE for multi-replica use.
    # Limits key on the authenticated user id when a valid bearer token is present, and
    # fall back to the client IP otherwise (see app/ratelimit.py).
    ratelimit_default: str = "200/minute"
    ratelimit_auth: str = "10/minute"
    ratelimit_upload: str = "30/minute"
    ratelimit_agent: str = "60/minute"
    ratelimit_storage: str = "memory://"

    # --- Observability ---
    log_level: str = "INFO"
    # "json" for machine-parsable production logs, "console" for readable dev output.
    log_format: str = "json"
    # Persist auth/admin/data events to the audit_log table in addition to stdout.
    audit_to_db: bool = True

    # --- Schema management ---
    # Dev convenience: create tables from the ORM metadata on startup. Set False in
    # production and run ``alembic upgrade head`` instead.
    auto_create_tables: bool = True

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
