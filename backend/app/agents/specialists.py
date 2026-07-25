"""The specialist agents. Each is a PydanticAI ``Agent`` with a typed ``output_type``
and a tool allowlist (read-only for Advise/Chat; write tools are added in later phases).

Phase 1 ships the two lowest-risk agents — the EDA Analyst (Advise) and the Data Analyst
(Chat) — both read-only. Later phases add the Profiler, Cleaning Agent, Modeling
Strategist, Evaluation Critic, and the Forge Master orchestrator here.
"""
from __future__ import annotations

from typing import Any

from pydantic_ai import Agent

from . import tools
from .deps import AgentDeps
from .schemas import EdaNarrative

EDA_ANALYST_PROMPT = """\
You are the EDA Analyst for PipeForge, an AutoML platform. You are given a dataset and
its exploratory-data-analysis summary. Use the tools to read the schema and EDA stats,
then produce a concise, decision-useful analysis:
- insights: concrete observations (distributions, cardinality, correlations).
- risks: things that would hurt modelling — target leakage, class imbalance, constant or
  highly-correlated features, heavy missingness, look-ahead in time series.
- hypotheses: modelling directions worth trying.
Be specific and reference column names. Do not invent columns you have not seen via the
tools. You cannot modify the run — you only advise.
"""

CHAT_PROMPT = """\
You are the PipeForge Data Analyst. Answer the user's questions about their dataset and
this run's results using the read-only tools (schema/stats, leaderboard, model details).
Ground every claim in tool output and cite column or model names. If something is not
available in the tools, say so plainly rather than guessing. You cannot change the run.
"""


def build_eda_analyst(model: Any) -> Agent[AgentDeps, EdaNarrative]:
    """Advise-mode agent: narrates insights/risks/hypotheses over a completed run."""
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=EdaNarrative,
        system_prompt=EDA_ANALYST_PROMPT,
        tools=[tools.profile_dataset, tools.query_eda_stats, tools.suggest_task_and_target],
        name="eda_analyst",
    )


def build_chat_agent(model: Any) -> Agent[AgentDeps, str]:
    """Chat-mode conversational analyst over a completed run (read-only tools)."""
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=str,
        system_prompt=CHAT_PROMPT,
        tools=list(tools.READ_ONLY_TOOLS),
        name="chat",
    )
