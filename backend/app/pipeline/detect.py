"""Auto-suggest the problem type and candidate target columns from a schema.

The user can always override these suggestions in the UI; this only provides sane
defaults so the common case is one click.
"""
from __future__ import annotations

from typing import Any


def _columns(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return schema.get("columns", [])


def suggest(schema: dict[str, Any], n_rows: int) -> dict[str, Any]:
    """Return suggested task type, candidate targets, and datetime columns.

    Rules (heuristic, overridable):
    - A datetime column + a numeric column strongly implies a time-series problem.
    - The last column is the conventional target; if it is low-cardinality or
      categorical => classification, if continuous numeric => regression.
    """
    cols = _columns(schema)
    datetime_cols = [c["name"] for c in cols if c["semantic"] == "datetime"]
    numeric_cols = [c for c in cols if c["semantic"] == "numeric"]

    candidates: list[dict[str, str]] = []

    # Time-series signal: at least one datetime column and something numeric to forecast.
    if datetime_cols and numeric_cols:
        suggested_task = "timeseries"
        for c in numeric_cols:
            candidates.append(
                {"column": c["name"], "reason": "Numeric series to forecast over the datetime index."}
            )
    else:
        # Tabular: guess the target as the last column.
        target = cols[-1] if cols else None
        suggested_task = "classification"
        if target is not None:
            n_unique = target["n_unique"]
            if target["semantic"] == "numeric" and n_unique > max(20, 0.1 * max(n_rows, 1)):
                suggested_task = "regression"
                reason = "Continuous numeric column (many unique values)."
            else:
                suggested_task = "classification"
                reason = f"Low-cardinality column ({n_unique} classes)."
            candidates.append({"column": target["name"], "reason": reason})

        # Offer a few other plausible targets.
        for c in cols[:-1] if len(cols) > 1 else []:
            if c["semantic"] in ("numeric", "categorical", "boolean") and c["n_unique"] > 1:
                candidates.append(
                    {"column": c["name"], "reason": f"{c['semantic']} column, {c['n_unique']} unique."}
                )
            if len(candidates) >= 6:
                break

    return {
        "suggested_task": suggested_task,
        "candidate_targets": candidates,
        "datetime_columns": datetime_cols,
    }
