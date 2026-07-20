"""Data cleaning / ETL stage.

Takes a raw DataFrame plus a cleaning config and returns a cleaned DataFrame together
with a report describing what was changed, so the UI can show the user exactly what
happened to their data.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _coerce_datetimes(df: pd.DataFrame) -> list[str]:
    """Best-effort parse object columns that look like dates. Returns coerced names."""
    coerced: list[str] = []
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().astype(str).head(200)
            if sample.empty:
                continue
            parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
            if parsed.notna().mean() > 0.9:
                df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
                coerced.append(str(col))
    return coerced


def clean_dataframe(df: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the configured cleaning steps and return (clean_df, report)."""
    df = df.copy()
    report: dict[str, Any] = {"steps": [], "initial_shape": list(df.shape)}

    coerced = _coerce_datetimes(df)
    if coerced:
        report["steps"].append({"op": "coerce_datetime", "columns": coerced})

    # Duplicate rows.
    if config.get("drop_duplicates", True):
        before = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        removed = before - len(df)
        if removed:
            report["steps"].append({"op": "drop_duplicates", "rows_removed": removed})

    # Constant columns (zero variance / single value).
    if config.get("drop_constant_columns", True):
        constant = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
        if constant:
            df = df.drop(columns=constant)
            report["steps"].append({"op": "drop_constant_columns", "columns": constant})

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = [
        c for c in df.columns if c not in numeric_cols and not pd.api.types.is_datetime64_any_dtype(df[c])
    ]

    # Numeric imputation.
    num_strategy = config.get("impute_numeric", "median")
    filled_numeric: dict[str, int] = {}
    for c in numeric_cols:
        n_missing = int(df[c].isna().sum())
        if n_missing == 0:
            continue
        if num_strategy == "median":
            df[c] = df[c].fillna(df[c].median())
        elif num_strategy == "mean":
            df[c] = df[c].fillna(df[c].mean())
        elif num_strategy == "zero":
            df[c] = df[c].fillna(0)
        elif num_strategy == "drop":
            df = df.dropna(subset=[c])
        filled_numeric[str(c)] = n_missing
    if filled_numeric:
        report["steps"].append(
            {"op": "impute_numeric", "strategy": num_strategy, "columns": filled_numeric}
        )

    # Categorical imputation.
    cat_strategy = config.get("impute_categorical", "mode")
    filled_cat: dict[str, int] = {}
    for c in categorical_cols:
        n_missing = int(df[c].isna().sum())
        if n_missing == 0:
            continue
        if cat_strategy == "mode":
            mode = df[c].mode(dropna=True)
            df[c] = df[c].fillna(mode.iloc[0] if not mode.empty else "unknown")
        elif cat_strategy == "constant":
            df[c] = df[c].fillna("unknown")
        elif cat_strategy == "drop":
            df = df.dropna(subset=[c])
        filled_cat[str(c)] = n_missing
    if filled_cat:
        report["steps"].append(
            {"op": "impute_categorical", "strategy": cat_strategy, "columns": filled_cat}
        )

    # Outlier handling (numeric only).
    outlier_method = config.get("outlier_method", "none")
    if outlier_method != "none" and numeric_cols:
        clipped: dict[str, int] = {}
        for c in numeric_cols:
            series = df[c]
            if outlier_method == "iqr":
                q1, q3 = series.quantile(0.25), series.quantile(0.75)
                iqr = q3 - q1
                low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            else:  # zscore
                mean, std = series.mean(), series.std(ddof=0)
                low, high = mean - 3 * std, mean + 3 * std
            n_out = int(((series < low) | (series > high)).sum())
            if n_out:
                df[c] = series.clip(low, high)
                clipped[str(c)] = n_out
        if clipped:
            report["steps"].append(
                {"op": "clip_outliers", "method": outlier_method, "columns": clipped}
            )

    report["final_shape"] = list(df.shape)
    return df.reset_index(drop=True), report
