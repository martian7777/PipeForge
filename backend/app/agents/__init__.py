"""Agentic AI layer for PipeForge.

Specialist LLM agents reason about the decisions the deterministic ``pipeline/*``
modules otherwise hardcode. The pipeline functions become the agents' *tools*: agents
decide, the tested pipeline executes. The whole layer is additive — with
``PIPEFORGE_LLM_PROVIDER=off`` (the default) nothing here runs and the classic pipeline
is unaffected.

Built on PydanticAI so every agent has a typed ``output_type`` and the provider is
pluggable (Anthropic / OpenAI / Ollama). See docs/ROADMAP.md.
"""
