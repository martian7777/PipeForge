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


def _build_model(provider: str, model_id: str) -> Any:
    """Construct a PydanticAI model instance for ``provider``/``model_id``."""
    if provider == "off":
        raise ProviderError(
            "The agent layer is disabled. Set PIPEFORGE_LLM_PROVIDER to "
            "anthropic, openai, or ollama (and PIPEFORGE_LLM_API_KEY)."
        )

    if provider == "anthropic":
        if not settings.llm_api_key:
            raise ProviderError("PIPEFORGE_LLM_API_KEY is required for the anthropic provider")
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(model_id, provider=AnthropicProvider(api_key=settings.llm_api_key))

    if provider in ("openai", "ollama"):
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if provider == "ollama":
            base_url = settings.llm_base_url or "http://localhost:11434/v1"
            api_key = settings.llm_api_key or "ollama"  # Ollama ignores the key but the SDK wants one
        else:
            base_url = settings.llm_base_url or None
            if not settings.llm_api_key:
                raise ProviderError("PIPEFORGE_LLM_API_KEY is required for the openai provider")
            api_key = settings.llm_api_key
        return OpenAIModel(model_id, provider=OpenAIProvider(api_key=api_key, base_url=base_url))

    raise ProviderError(f"Unknown LLM provider: {provider!r}")


def get_model(
    agent_name: str,
    user: "Optional[User]" = None,
    db: "Optional[Session]" = None,
) -> Any:
    """Resolve and build the PydanticAI model an agent should run on."""
    provider, model_id = _resolve(agent_name, user, db)
    return _build_model(provider, model_id)


def available_models() -> dict[str, list[str]]:
    """Curated per-provider model lists for the settings dropdown."""
    return {
        "anthropic": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
        "openai": ["gpt-4o", "gpt-4o-mini", "o4-mini"],
        "ollama": ["llama3.1", "mistral", "qwen2.5"],
    }


def is_enabled() -> bool:
    """True when a real provider is configured (used to gate the API surface)."""
    return settings.llm_provider != "off"
