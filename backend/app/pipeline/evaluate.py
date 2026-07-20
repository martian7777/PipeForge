"""Task-specific metrics and evaluation-plot payloads (Plotly-friendly)."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
    roc_curve,
)


def classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_proba: Optional[np.ndarray], n_classes: int
) -> dict[str, float]:
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }
    if y_proba is not None:
        try:
            if n_classes == 2:
                metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba[:, 1]))
            else:
                metrics["roc_auc"] = float(
                    roc_auc_score(y_true, y_proba, multi_class="ovr", average="weighted")
                )
        except ValueError:
            pass
    return metrics


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def classification_plots(
    y_true: np.ndarray, y_pred: np.ndarray, y_proba: Optional[np.ndarray], classes: list[str]
) -> dict[str, Any]:
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(classes))))
    plots: dict[str, Any] = {
        "confusion_matrix": {"labels": classes, "z": cm.tolist()},
    }
    # Binary ROC curve.
    if y_proba is not None and len(classes) == 2:
        try:
            fpr, tpr, _ = roc_curve(y_true, y_proba[:, 1])
            plots["roc"] = {"fpr": [float(v) for v in fpr], "tpr": [float(v) for v in tpr]}
        except ValueError:
            pass
    return plots


def regression_plots(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    residuals = (y_true - y_pred).astype(float)
    # Cap scatter payload size for very large holdouts.
    idx = np.arange(len(y_true))
    if len(idx) > 2000:
        idx = np.random.default_rng(0).choice(idx, 2000, replace=False)
    return {
        "pred_vs_actual": {
            "actual": [float(v) for v in np.asarray(y_true)[idx]],
            "predicted": [float(v) for v in np.asarray(y_pred)[idx]],
        },
        "residuals": {
            "predicted": [float(v) for v in np.asarray(y_pred)[idx]],
            "residual": [float(v) for v in residuals[idx]],
        },
    }


def primary_metric(task_type: str) -> tuple[str, bool]:
    """Return (metric_name, higher_is_better) used to rank the leaderboard."""
    if task_type == "classification":
        return "f1_weighted", True
    return "rmse", False
