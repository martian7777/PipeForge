"""Feature engineering: build a picklable sklearn preprocessor and prepare X/y.

The preprocessor is a ColumnTransformer so it can be bundled with each model into a
single sklearn Pipeline — that way the persisted artifact transforms raw input rows the
same way at prediction time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    FunctionTransformer,
    OneHotEncoder,
    StandardScaler,
)


def _expand_datetimes(X: pd.DataFrame) -> pd.DataFrame:
    """Module-level (picklable) transformer: datetime columns -> numeric parts."""
    out = pd.DataFrame(index=X.index)
    for col in X.columns:
        s = pd.to_datetime(X[col], errors="coerce")
        out[f"{col}__year"] = s.dt.year
        out[f"{col}__month"] = s.dt.month
        out[f"{col}__day"] = s.dt.day
        out[f"{col}__dayofweek"] = s.dt.dayofweek
    return out.fillna(-1)


@dataclass
class FeatureSpec:
    numeric: list[str]
    categorical: list[str]
    datetime: list[str]

    @property
    def all_features(self) -> list[str]:
        return self.numeric + self.categorical + self.datetime


def infer_feature_spec(df: pd.DataFrame, target: Optional[str]) -> FeatureSpec:
    """Classify feature columns (excluding the target) into numeric/categorical/datetime."""
    numeric, categorical, datetime_cols = [], [], []
    for col in df.columns:
        if col == target:
            continue
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            datetime_cols.append(col)
        elif pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            numeric.append(col)
        else:
            categorical.append(col)
    return FeatureSpec(numeric, categorical, datetime_cols)


def build_preprocessor(spec: FeatureSpec) -> ColumnTransformer:
    """Assemble the ColumnTransformer for the given feature spec."""
    transformers = []
    if spec.numeric:
        transformers.append(
            (
                "num",
                Pipeline(
                    [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                ),
                spec.numeric,
            )
        )
    if spec.categorical:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", max_categories=50)),
                    ]
                ),
                spec.categorical,
            )
        )
    if spec.datetime:
        transformers.append(
            (
                "dt",
                Pipeline(
                    [
                        ("expand", FunctionTransformer(_expand_datetimes, validate=False)),
                        ("impute", SimpleImputer(strategy="median")),
                    ]
                ),
                spec.datetime,
            )
        )
    return ColumnTransformer(transformers=transformers, remainder="drop", sparse_threshold=0.0)


def prepare_target(y: pd.Series, task_type: str) -> tuple[np.ndarray, Optional[list[str]]]:
    """Return the model target array and, for classification, the ordered class labels."""
    if task_type == "classification":
        classes = sorted(y.dropna().astype(str).unique().tolist())
        mapping = {c: i for i, c in enumerate(classes)}
        encoded = y.astype(str).map(mapping).to_numpy()
        return encoded, classes
    return pd.to_numeric(y, errors="coerce").to_numpy(), None
