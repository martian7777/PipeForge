"""Model artifact registry: persist trained pipelines and run predictions with them.

Artifacts are stored under the sharded artifact directory and bundle the full sklearn
Pipeline (preprocessor + model) plus the metadata needed to decode predictions.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from ..storage import artifact_path


def save_model(
    pipeline: Pipeline,
    task_type: str,
    target: str,
    feature_columns: list[str],
    classes: Optional[list[str]],
) -> str:
    """Persist a fitted pipeline; return the storage key."""
    key = f"{uuid.uuid4().hex}.joblib"
    payload = {
        "pipeline": pipeline,
        "task_type": task_type,
        "target": target,
        "feature_columns": feature_columns,
        "classes": classes,
    }
    joblib.dump(payload, artifact_path(key))
    return key


def load_model(key: str) -> dict[str, Any]:
    path = artifact_path(key, create=False)
    if not path.exists():
        raise FileNotFoundError(f"Artifact {key} not found")
    return joblib.load(path)


def predict(key: str, df: pd.DataFrame) -> dict[str, Any]:
    """Run predictions on new rows using a stored model."""
    bundle = load_model(key)
    pipeline: Pipeline = bundle["pipeline"]
    feature_columns: list[str] = bundle["feature_columns"]
    classes: Optional[list[str]] = bundle["classes"]

    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Input is missing required feature columns: {missing}")

    X = df[feature_columns]
    preds = pipeline.predict(X)
    if bundle["task_type"] == "classification" and classes is not None:
        labels = [classes[int(p)] if 0 <= int(p) < len(classes) else str(p) for p in preds]
        return {"predictions": labels}
    return {"predictions": [float(p) for p in preds]}


def artifact_file(key: str) -> Path:
    return artifact_path(key, create=False)
