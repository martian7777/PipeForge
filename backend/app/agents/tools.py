"""Agent tools — thin ``RunContext`` wrappers over the existing pipeline + DB functions.

The whole reuse principle lives here: each tool calls an already-tested ``pipeline/*``
function or a scoped DB read/write. Agents reason and call these; the deterministic code
executes. Read-only tools (``profile_dataset``, ``query_eda_stats``, ``read_*``) are the
only ones exposed to the Chat and Advise agents; write tools are gated to
Copilot/Autopilot by which tools each agent is constructed with.

Data sent to the LLM is schema/stats/samples — never the full dataset — for privacy and
token cost.
"""
from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from ..pipeline import detect, eda, ingest
from .deps import AgentDeps

# ``model_zoo`` and ``registry`` pull the ML stack (sklearn/xgboost/joblib); import them
# lazily so read-only Advise/Chat agents don't need that stack loaded.

# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


def profile_dataset(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
    """Return the dataset's inferred schema plus per-column summary statistics.

    Sends column names, semantic types, missing/unique counts and small samples —
    never the full data.
    """
    ds = ctx.deps.dataset
    schema = ds.schema_json or ingest.infer_schema(ctx.deps.dataframe())
    return {
        "filename": ds.filename,
        "n_rows": ds.n_rows,
        "n_cols": ds.n_cols,
        "columns": schema.get("columns", []),
    }


def suggest_task_and_target(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
    """Heuristic task-type + candidate-target suggestion (wraps ``detect.suggest``)."""
    ds = ctx.deps.dataset
    return detect.suggest(ds.schema_json or {}, ds.n_rows)


def query_eda_stats(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
    """Return the run's EDA summary + chart metadata.

    Uses the stored ``Run.eda_json`` when a run has already produced it; otherwise runs
    EDA on the fly (read-only — no artifacts persisted). Chart payloads are trimmed to
    titles/kinds to keep the response small.
    """
    run = ctx.deps.run
    payload: dict[str, Any]
    if run is not None and run.eda_json:
        payload = run.eda_json
    else:
        task_type = run.task_type if run is not None else "classification"
        target = run.target_col if run is not None else None
        payload = eda.run_eda(ctx.deps.dataframe(), task_type, target, report_path=None)
    charts = [
        {"id": c.get("id"), "kind": c.get("kind"), "title": c.get("title")}
        for c in payload.get("charts", [])
    ]
    return {"summary": payload.get("summary", {}), "charts": charts}


def list_candidate_models(ctx: RunContext[AgentDeps], task_type: str) -> list[dict[str, str]]:
    """The candidate model zoo for a task type (name + family), for the strategist."""
    from ..pipeline import model_zoo  # lazy: pulls the ML stack only when actually used

    try:
        zoo = model_zoo.zoo_for(task_type)
    except Exception:  # noqa: BLE001 - unknown/unsupported task type
        return []
    return [{"name": c.name, "family": c.family} for c in zoo]


def read_leaderboard(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
    """Ranked trained models for the run (name, family, metrics, rank)."""
    from ..models import ModelResult  # local import avoids an import cycle

    run = ctx.deps.run
    if run is None:
        return []
    rows = (
        ctx.deps.db.query(ModelResult)
        .filter(ModelResult.run_id == run.id)
        .order_by(ModelResult.rank)
        .all()
    )
    return [
        {
            "id": r.id,
            "model_name": r.model_name,
            "family": r.family,
            "metrics": r.metrics_json,
            "rank": r.rank,
        }
        for r in rows
    ]


def read_model_detail(ctx: RunContext[AgentDeps], model_id: int) -> dict[str, Any]:
    """Full metrics + eval-plot metadata for one trained model."""
    from ..models import ModelResult

    r = ctx.deps.db.get(ModelResult, model_id)
    if r is None or (ctx.deps.run is not None and r.run_id != ctx.deps.run.id):
        return {"error": f"model {model_id} not found for this run"}
    return {
        "id": r.id,
        "model_name": r.model_name,
        "family": r.family,
        "metrics": r.metrics_json,
        "plots": list((r.plots_json or {}).keys()),
        "rank": r.rank,
    }


# Convenient bundles for constructing agents with the right tool allowlist.
READ_ONLY_TOOLS = [
    profile_dataset,
    suggest_task_and_target,
    query_eda_stats,
    read_leaderboard,
    read_model_detail,
]

__all__ = [
    "profile_dataset",
    "suggest_task_and_target",
    "query_eda_stats",
    "list_candidate_models",
    "read_leaderboard",
    "read_model_detail",
    "READ_ONLY_TOOLS",
]
