"""AutoML training orchestrator.

Sweeps the model zoo, fits each candidate on a train split inside a full sklearn
Pipeline (preprocessor + model), scores it on a holdout, collects metrics + eval-plot
payloads, and ranks the results into a leaderboard. Mirrors what an AutoML
`compare_models` does, but transparently and with no heavy framework dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from . import evaluate, features, model_zoo

ProgressCb = Callable[[float, str], None]


@dataclass
class TrainedModel:
    name: str
    family: str
    metrics: dict[str, float]
    plots: dict[str, Any]
    pipeline: Pipeline
    rank: int = 0
    error: Optional[str] = None


@dataclass
class TrainingResult:
    models: list[TrainedModel]
    classes: Optional[list[str]]
    primary_metric: str
    n_train: int
    n_test: int
    feature_spec: dict[str, list[str]] = field(default_factory=dict)


def _feature_importance(pipeline: Pipeline, top: int = 20) -> Optional[dict[str, Any]]:
    """Extract top feature importances / coefficients if the model exposes them."""
    try:
        pre = pipeline.named_steps["pre"]
        model = pipeline.named_steps["model"]
        names = list(pre.get_feature_names_out())
    except Exception:  # noqa: BLE001
        return None

    values: Optional[np.ndarray] = None
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        coef = np.asarray(model.coef_, dtype=float)
        values = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
    if values is None or len(values) != len(names):
        return None

    order = np.argsort(values)[::-1][:top]
    return {
        "features": [str(names[i]) for i in order],
        "importance": [float(values[i]) for i in order],
    }


def train_models(
    df: pd.DataFrame,
    target: str,
    task_type: str,
    progress_cb: Optional[ProgressCb] = None,
    test_size: float = 0.2,
) -> TrainingResult:
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not in data")

    # Drop rows with a missing target — we can't learn from those.
    df = df[df[target].notna()].reset_index(drop=True)
    if len(df) < 10:
        raise ValueError("Not enough rows with a non-missing target to train (need >= 10).")

    spec = features.infer_feature_spec(df, target)
    if not spec.all_features:
        raise ValueError("No usable feature columns found.")

    X = df[spec.all_features]
    y_raw = df[target]
    y, classes = features.prepare_target(y_raw, task_type)

    # Guard against NaN targets after numeric coercion (regression).
    mask = ~pd.isna(y)
    X, y = X.loc[mask].reset_index(drop=True), y[mask]

    stratify = y if (task_type == "classification" and pd.Series(y).value_counts().min() >= 2) else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=stratify
    )

    metric_name, higher_better = evaluate.primary_metric(task_type)
    candidates = model_zoo.zoo_for(task_type)
    trained: list[TrainedModel] = []

    for i, cand in enumerate(candidates):
        if progress_cb:
            progress_cb(i / len(candidates), f"Training {cand.name}")
        pre = features.build_preprocessor(spec)
        pipe = Pipeline([("pre", pre), ("model", cand.factory())])
        try:
            pipe.fit(X_train, y_train)
            y_pred = pipe.predict(X_test)
            if task_type == "classification":
                proba = pipe.predict_proba(X_test) if hasattr(pipe, "predict_proba") else None
                metrics = evaluate.classification_metrics(y_test, y_pred, proba, len(classes or []))
                plots = evaluate.classification_plots(y_test, y_pred, proba, classes or [])
            else:
                metrics = evaluate.regression_metrics(y_test, y_pred)
                plots = evaluate.regression_plots(y_test, y_pred)
            fi = _feature_importance(pipe)
            if fi:
                plots["feature_importance"] = fi
            trained.append(TrainedModel(cand.name, cand.family, metrics, plots, pipe))
        except Exception as exc:  # noqa: BLE001 - a single model failing shouldn't kill the run
            trained.append(
                TrainedModel(cand.name, cand.family, {}, {}, pipe, error=str(exc))
            )

    # Rank successful models by the primary metric.
    ok = [m for m in trained if m.metrics.get(metric_name) is not None]
    failed = [m for m in trained if m.metrics.get(metric_name) is None]
    ok.sort(key=lambda m: m.metrics[metric_name], reverse=higher_better)
    for rank, m in enumerate(ok, start=1):
        m.rank = rank
    if not ok:
        raise ValueError("All candidate models failed to train.")

    if progress_cb:
        progress_cb(1.0, "Training complete")

    return TrainingResult(
        models=ok + failed,
        classes=classes,
        primary_metric=metric_name,
        n_train=len(X_train),
        n_test=len(X_test),
        feature_spec={"numeric": spec.numeric, "categorical": spec.categorical, "datetime": spec.datetime},
    )
