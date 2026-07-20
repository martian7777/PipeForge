"""Exploratory data analysis.

Produces two things from a cleaned DataFrame:
1. Plotly-friendly chart payloads + a summary (consumed by the React EDA dashboard).
2. A self-contained static HTML report saved to the reports directory.

We compute everything with pandas/numpy directly (rather than a heavy profiling
dependency) so the stage is fast, predictable, and easy to run at scale.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

MAX_NUMERIC_CHARTS = 12
MAX_CATEGORICAL_CHARTS = 12
MAX_CATEGORIES = 20


def _numeric_cols(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes(include=[np.number]).columns.tolist()


def _datetime_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]


def _categorical_cols(df: pd.DataFrame) -> list[str]:
    num, dt = set(_numeric_cols(df)), set(_datetime_cols(df))
    return [c for c in df.columns if c not in num and c not in dt]


def _summary(df: pd.DataFrame) -> dict[str, Any]:
    missing = df.isna().sum()
    return {
        "n_rows": int(df.shape[0]),
        "n_cols": int(df.shape[1]),
        "n_numeric": len(_numeric_cols(df)),
        "n_categorical": len(_categorical_cols(df)),
        "n_datetime": len(_datetime_cols(df)),
        "total_missing": int(missing.sum()),
        "missing_by_column": {str(k): int(v) for k, v in missing.items() if v > 0},
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
    }


def _chart(id_: str, kind: str, title: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"id": id_, "kind": kind, "title": title, "data": data}


def build_charts(df: pd.DataFrame, task_type: str, target: Optional[str]) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    numeric = _numeric_cols(df)
    categorical = _categorical_cols(df)
    datetimes = _datetime_cols(df)

    # Missingness overview.
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if not missing.empty:
        charts.append(
            _chart(
                "missingness",
                "bar",
                "Missing values by column",
                {"x": [str(c) for c in missing.index], "y": [int(v) for v in missing.values]},
            )
        )

    # Numeric distributions.
    for c in numeric[:MAX_NUMERIC_CHARTS]:
        series = df[c].dropna()
        if series.empty:
            continue
        counts, edges = np.histogram(series, bins=min(30, max(5, series.nunique())))
        charts.append(
            _chart(
                f"hist_{c}",
                "histogram",
                f"Distribution of {c}",
                {"bins": [float(e) for e in edges], "counts": [int(v) for v in counts]},
            )
        )

    # Categorical value counts.
    for c in categorical[:MAX_CATEGORICAL_CHARTS]:
        vc = df[c].astype("string").value_counts(dropna=True).head(MAX_CATEGORIES)
        if vc.empty:
            continue
        charts.append(
            _chart(
                f"cat_{c}",
                "bar",
                f"Top categories of {c}",
                {"x": [str(i) for i in vc.index], "y": [int(v) for v in vc.values]},
            )
        )

    # Correlation heatmap.
    if len(numeric) >= 2:
        corr = df[numeric].corr(numeric_only=True).fillna(0.0)
        charts.append(
            _chart(
                "correlation",
                "heatmap",
                "Correlation (numeric features)",
                {
                    "labels": [str(c) for c in corr.columns],
                    "z": [[round(float(v), 3) for v in row] for row in corr.values],
                },
            )
        )

    # Target relationships.
    if target and target in df.columns:
        if task_type == "regression" and target in numeric:
            for c in [n for n in numeric if n != target][:6]:
                sub = df[[c, target]].dropna()
                if sub.empty:
                    continue
                charts.append(
                    _chart(
                        f"scatter_{c}",
                        "scatter",
                        f"{c} vs {target}",
                        {"x": [float(v) for v in sub[c]], "y": [float(v) for v in sub[target]]},
                    )
                )
        elif task_type == "classification":
            vc = df[target].astype("string").value_counts().head(MAX_CATEGORIES)
            charts.append(
                _chart(
                    "class_balance",
                    "bar",
                    f"Class balance: {target}",
                    {"x": [str(i) for i in vc.index], "y": [int(v) for v in vc.values]},
                )
            )

    # Time series line(s).
    if task_type == "timeseries" and datetimes and target and target in numeric:
        dt = datetimes[0]
        sub = df[[dt, target]].dropna().sort_values(dt)
        charts.append(
            _chart(
                "timeseries",
                "line",
                f"{target} over {dt}",
                {
                    "x": [pd.Timestamp(v).isoformat() for v in sub[dt]],
                    "y": [float(v) for v in sub[target]],
                },
            )
        )

    return charts


def render_html_report(
    df: pd.DataFrame, summary: dict[str, Any], report_path: Path
) -> None:
    """Write a self-contained static HTML report of describe() + dtypes + missingness."""
    desc = df.describe(include="all").transpose()
    desc_html = desc.to_html(classes="tbl", border=0, na_rep="â€”", float_format=lambda x: f"{x:.4g}")
    missing = summary["missing_by_column"]
    missing_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{v}</td></tr>" for k, v in missing.items()
    ) or "<tr><td colspan=2>No missing values</td></tr>"

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>PipeForge EDA Report</title>
<style>
 body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:32px;background:#0f1220;color:#e6e8f0}}
 h1{{margin:0 0 4px}} .muted{{color:#9aa3c0}}
 .grid{{display:flex;gap:24px;flex-wrap:wrap;margin:18px 0}}
 .stat{{background:#181c2f;border:1px solid #2b3150;border-radius:12px;padding:14px 18px}}
 .stat b{{font-size:22px}}
 table.tbl{{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}}
 .tbl th,.tbl td{{border-bottom:1px solid #2b3150;padding:6px 10px;text-align:left}}
 .tbl th{{color:#9aa3c0}} .wrap{{overflow-x:auto}}
</style></head><body>
<h1>PipeForge â€” EDA Report</h1>
<div class="muted">{summary['n_rows']:,} rows Ã— {summary['n_cols']} columns Â·
 {summary['total_missing']:,} missing cells</div>
<div class="grid">
 <div class="stat"><div class="muted">Numeric</div><b>{summary['n_numeric']}</b></div>
 <div class="stat"><div class="muted">Categorical</div><b>{summary['n_categorical']}</b></div>
 <div class="stat"><div class="muted">Datetime</div><b>{summary['n_datetime']}</b></div>
 <div class="stat"><div class="muted">Memory</div><b>{summary['memory_bytes']/1e6:.1f} MB</b></div>
</div>
<h2>Column statistics</h2><div class="wrap">{desc_html}</div>
<h2>Missing values</h2><table class="tbl"><tr><th>Column</th><th>Missing</th></tr>{missing_rows}</table>
</body></html>"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(doc, encoding="utf-8")


def run_eda(
    df: pd.DataFrame,
    task_type: str,
    target: Optional[str],
    report_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Full EDA: summary + charts (+ optional HTML report). Returns a dict payload."""
    summary = _summary(df)
    charts = build_charts(df, task_type, target)
    if report_path is not None:
        render_html_report(df, summary, report_path)
    return {"summary": summary, "charts": charts}
