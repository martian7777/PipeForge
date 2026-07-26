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
from .schemas import CleaningPlan, EdaNarrative, EvalVerdict, ModelingPlan, ProfileReport

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


# --- Copilot / Autopilot specialists (propose typed plans; the orchestrator executes) ---

PROFILER_PROMPT = """\
You are the Profiler. Inspect the dataset's schema and samples with the tools, then
decide the most likely task_type (classification/regression/timeseries) and the target
column, and flag data-quality issues. Prefer the heuristic suggestion but override it if
the data clearly says otherwise. Reference real column names only.
"""

CLEANING_PROMPT = """\
You are the Cleaning Agent. Given the dataset profile, propose a cleaning strategy:
imputation for numeric and categorical columns, whether to drop duplicates / constant
columns, and an outlier method. Justify each choice per affected column. Return a
CleaningPlan — the user will review it before it runs.
"""

MODELING_PROMPT = """\
You are the Modeling Strategist. Given the profile and EDA, choose a sensible subset of
candidate models to train (use list_candidate_models for the task type) and a test split
size. Favour a small, diverse set over the whole zoo when the dataset is small.

You may also propose hyperparameter tuning: set tune=true and provide, per selected model
name, a small grid of candidate values (e.g. {"Random Forest": {"n_estimators": [100, 300],
"max_depth": [null, 10]}}). Keep grids small — a few values per parameter. Return a
ModelingPlan; the user reviews it before training runs.
"""

CRITIC_PROMPT = """\
You are the Evaluation Critic. Read the leaderboard and model details, then recommend the
best model by id and justify it. Use read_feature_importance on the top model to check its
explanation: a single feature dominating often signals target leakage; incoherent drivers
signal an untrustworthy model. Populate key_drivers with the model's top features and list
warnings (overfitting, leakage, a metric that looks too good). Ground every claim in what
you read.
"""


def build_profiler(model: Any) -> Agent[AgentDeps, ProfileReport]:
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=ProfileReport,
        system_prompt=PROFILER_PROMPT,
        tools=[tools.profile_dataset, tools.suggest_task_and_target],
        name="profiler",
    )


def build_cleaning_agent(model: Any) -> Agent[AgentDeps, CleaningPlan]:
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=CleaningPlan,
        system_prompt=CLEANING_PROMPT,
        tools=[tools.profile_dataset, tools.query_eda_stats],
        name="cleaning",
    )


def build_modeling_strategist(model: Any) -> Agent[AgentDeps, ModelingPlan]:
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=ModelingPlan,
        system_prompt=MODELING_PROMPT,
        tools=[tools.profile_dataset, tools.query_eda_stats, tools.list_candidate_models],
        name="modeling",
    )


def build_critic(model: Any) -> Agent[AgentDeps, EvalVerdict]:
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=EvalVerdict,
        system_prompt=CRITIC_PROMPT,
        tools=[tools.read_leaderboard, tools.read_model_detail, tools.read_feature_importance],
        name="critic",
    )
