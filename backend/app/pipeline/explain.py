"""Model explainability (Phase 4).

Provides feature attributions the Evaluation Critic reads to sanity-check a model
(dominant feature => possible leakage, sensible drivers => trustworthy).

``shap_summary`` computes SHAP values when the optional ``shap`` package is installed;
otherwise the pipeline falls back to the coefficient/importance attribution that
``train.py`` already extracts. ``top_drivers`` reads whichever attribution is present on a
stored ``plots_json`` payload — a pure dict read, so the Critic's tool needs no ML stack.
"""
from __future__ import annotations

from typing import Any, Optional


def shap_available() -> bool:
    try:
        import shap  # noqa: F401
    except Exception:  # noqa: BLE001 - optional dependency
        return False
    return True


def shap_summary(pipeline: Any, x_sample: Any, top: int = 20) -> Optional[dict[str, Any]]:
    """Mean absolute SHAP value per feature, or None if shap isn't available/usable.

    Runs on the preprocessed feature matrix so names line up with the model's inputs.
    """
    try:
        import numpy as np
        import shap

        pre = pipeline.named_steps["pre"]
        model = pipeline.named_steps["model"]
        names = list(pre.get_feature_names_out())
        x_trans = pre.transform(x_sample)
        # A small background keeps the (potentially expensive) explainer fast.
        explainer = shap.Explainer(model, x_trans)
        values = explainer(x_trans).values
        arr = np.asarray(values)
        if arr.ndim == 3:  # (n, features, classes) -> average over classes
            arr = np.abs(arr).mean(axis=2)
        mean_abs = np.abs(arr).mean(axis=0)
        if len(mean_abs) != len(names):
            return None
        order = np.argsort(mean_abs)[::-1][:top]
        return {
            "method": "shap",
            "features": [str(names[i]) for i in order],
            "importance": [float(mean_abs[i]) for i in order],
        }
    except Exception:  # noqa: BLE001 - explainability must never break training
        return None


def top_drivers(plots: dict[str, Any], k: int = 8) -> list[str]:
    """Top feature names from whichever attribution a model has (SHAP preferred)."""
    for key in ("shap", "feature_importance"):
        payload = (plots or {}).get(key)
        if isinstance(payload, dict) and payload.get("features"):
            return list(payload["features"])[:k]
    return []
