"""Typed ``output_type`` result contracts for each specialist agent.

Agents return these validated Pydantic objects (never free text between agents), so the
orchestrator hands one specialist's output to the next as structured input, and the
frontend renders them directly.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QualityFlag(BaseModel):
    column: str
    issue: str
    severity: str = Field(pattern="^(low|medium|high)$")


class ProfileReport(BaseModel):
    """Profiler output: inferred task/target + data-quality assessment."""

    task_type: str
    target_col: str | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    rationale: str


class ColumnCleaningReason(BaseModel):
    column: str
    action: str
    reason: str


class CleaningPlan(BaseModel):
    """Cleaning Agent output: a validated CleaningConfig plus per-column reasoning."""

    # Mirrors schemas.CleaningConfig; re-validated there before execution.
    drop_duplicates: bool = True
    impute_numeric: str = Field(default="median", pattern="^(median|mean|zero|drop)$")
    impute_categorical: str = Field(default="mode", pattern="^(mode|constant|drop)$")
    drop_constant_columns: bool = True
    outlier_method: str = Field(default="none", pattern="^(none|iqr|zscore)$")
    per_column_reasons: list[ColumnCleaningReason] = Field(default_factory=list)


class EdaNarrative(BaseModel):
    """EDA Analyst output: human-readable insights, risks, and hypotheses."""

    insights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    summary: str


class ModelingPlan(BaseModel):
    """Modeling Strategist output: which models to try, how to split, and (Phase 4) how
    to tune. ``hyperparameters`` maps a model name to param → candidate values; when
    ``tune`` is set, training runs a randomized search over those grids."""

    selected_models: list[str] = Field(default_factory=list)
    test_size: float = Field(default=0.2, ge=0.05, le=0.5)
    cv_strategy: str = "holdout"
    tune: bool = False
    hyperparameters: dict[str, dict[str, list[Any]]] = Field(default_factory=dict)
    rationale: str


class EvalVerdict(BaseModel):
    """Evaluation Critic output: model recommendation, caveats, and the features that
    drive the recommended model (read from its explanation)."""

    recommended_model_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    key_drivers: list[str] = Field(default_factory=list)
    justification: str
