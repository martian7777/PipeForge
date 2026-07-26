"""Pluggable LLM provider factory for the agent layer.

``get_model(agent_name, ...)`` resolves a PydanticAI model from the user's per-agent
``AgentConfig`` override, falling back to the system default for that agent's role
(``config.py``). This is the single place provider selection lives, so the rest of the
agent code never imports a provider SDK directly.

Model IDs default to Anthropic Claude tiers (Opus 4.8 for orchestration/analysis,
Haiku 4.5 for cheap sub-tasks, Sonnet 5 for chat) — see the ``llm_model_*`` settings.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ..config import settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import User
    from sqlalchemy.orm import Session


# Which system-default model role each agent uses when the user has no override.
ROLE_BY_AGENT: dict[str, str] = {
    "orchestrator": "orchestrator",
    "profiler": "cheap",
    "cleaning": "cheap",
    "eda_analyst": "analyst",
    "modeling": "analyst",
    "critic": "analyst",
    "chat": "chat",
}

# Human-friendly labels for the settings UI.
AGENT_LABELS: dict[str, str] = {
    "orchestrator": "Forge Master (orchestrator)",
    "profiler": "Profiler",
    "cleaning": "Cleaning Agent",
    "eda_analyst": "EDA Analyst",
    "modeling": "Modeling Strategist",
    "critic": "Evaluation Critic",
    "chat": "Data Analyst (chat)",
}


class ProviderError(RuntimeError):
    """Raised when the agent layer is misconfigured (no provider, missing key, ...)."""


def _default_model_id(role: str) -> str:
    return {
        "orchestrator": settings.llm_model_orchestrator,
        "analyst": settings.llm_model_analyst,
        "cheap": settings.llm_model_cheap,
        "chat": settings.llm_model_chat,
    }.get(role, settings.llm_model_analyst)


def _resolve(agent_name: str, user: "Optional[User]", db: "Optional[Session]") -> tuple[str, str]:
    """Return ``(provider, model_id)`` for an agent, honouring a per-user override."""
    provider = settings.llm_provider
    role = ROLE_BY_AGENT.get(agent_name, "analyst")
    model_id = _default_model_id(role)

    if user is not None and db is not None:
        from ..models import AgentConfig  # local import avoids a cycle at import time

        cfg = (
            db.query(AgentConfig)
            .filter(AgentConfig.user_id == user.id, AgentConfig.agent_name == agent_name)
            .one_or_none()
        )
        if cfg is not None:
            if not cfg.enabled:
                raise ProviderError(f"Agent '{agent_name}' is disabled in your settings")
            if cfg.provider:
                provider = cfg.provider
            if cfg.model:
                model_id = cfg.model
    return provider, model_id


# The provider registry. To add a provider, add one entry here (key env field, a builder,
# and a curated model list) — nothing else in the codebase needs to change.
PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "label": "Anthropic (Claude)",
        "key_setting": "anthropic_api_key",
        "models": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
    },
    "openai": {
        "label": "OpenAI (GPT)",
        "key_setting": "openai_api_key",
        "models": ["gpt-4o", "gpt-4o-mini", "o4-mini"],
    },
    "google": {
        "label": "Google (Gemini)",
        "key_setting": "google_api_key",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    },
    "ollama": {
        "label": "Ollama (local)",
        "key_setting": None,  # local; key optional
        "models": ["llama3.1", "mistral", "qwen2.5"],
    },
    "openai_compatible": {
        "label": "OpenAI-compatible (custom base URL)",
        "key_setting": None,
        "models": [],  # any model name your gateway serves
    },
}


def _key_for(provider: str) -> str:
    """Resolve a provider's API key: its dedicated setting, else the generic fallback."""
    key_setting = PROVIDERS.get(provider, {}).get("key_setting")
    specific = getattr(settings, key_setting) if key_setting else ""
    return specific or settings.llm_api_key


def _build_model(provider: str, model_id: str) -> Any:
    """Construct a PydanticAI model instance for ``provider``/``model_id``."""
    if provider == "off":
        raise ProviderError(
            "The agent layer is disabled. Set PIPEFORGE_LLM_PROVIDER to one of: "
            + ", ".join(k for k in PROVIDERS)
            + " (and the matching API key)."
        )
    if provider not in PROVIDERS:
        raise ProviderError(f"Unknown LLM provider: {provider!r}. Known: {', '.join(PROVIDERS)}")

    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        key = _key_for(provider) or _require_key(provider)
        return AnthropicModel(model_id, provider=AnthropicProvider(api_key=key))

    if provider == "google":
        # google-genai SDK (GoogleModel/GoogleProvider). Install the pydantic-ai google extra.
        try:
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "Google/Gemini support needs the pydantic-ai google extra: "
                "pip install 'pydantic-ai-slim[google]'"
            ) from exc
        key = _key_for(provider) or _require_key(provider)
        return GoogleModel(model_id, provider=GoogleProvider(api_key=key))

    # openai, ollama, and openai_compatible all use the OpenAI-compatible client.
    try:
        from pydantic_ai.models.openai import OpenAIModel
    except ImportError:
        from pydantic_ai.models.openai import OpenAIChatModel as OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if provider == "ollama":
        base_url = settings.llm_base_url or "http://localhost:11434/v1"
        api_key = _key_for(provider) or "ollama"  # Ollama ignores the key but the SDK wants one
    elif provider == "openai_compatible":
        base_url = settings.llm_base_url
        if not base_url:
            raise ProviderError("PIPEFORGE_LLM_BASE_URL is required for the openai_compatible provider")
        api_key = _key_for(provider) or "not-needed"
    else:  # openai
        base_url = settings.llm_base_url or None
        api_key = _key_for(provider) or _require_key(provider)
    return OpenAIModel(model_id, provider=OpenAIProvider(api_key=api_key, base_url=base_url))


def _require_key(provider: str) -> str:
    key_setting = PROVIDERS.get(provider, {}).get("key_setting")
    var = f"PIPEFORGE_{key_setting.upper()}" if key_setting else "PIPEFORGE_LLM_API_KEY"
    raise ProviderError(f"An API key is required for the {provider} provider — set {var} (or PIPEFORGE_LLM_API_KEY).")


def get_model(
    agent_name: str,
    user: "Optional[User]" = None,
    db: "Optional[Session]" = None,
) -> Any:
    """Resolve and build the PydanticAI model an agent should run on."""
    provider, model_id = _resolve(agent_name, user, db)
    return _build_model(provider, model_id)


def available_models() -> dict[str, list[str]]:
    """Curated per-provider model lists for the settings dropdown. Any model name your
    provider serves also works — the dropdown allows a free-text entry too."""
    return {name: list(p["models"]) for name, p in PROVIDERS.items()}


def provider_labels() -> dict[str, str]:
    """Human-friendly provider names for the settings UI."""
    return {name: p["label"] for name, p in PROVIDERS.items()}


def is_enabled() -> bool:
    """True when a real provider is configured (used to gate the API surface)."""
    return settings.llm_provider != "off"
