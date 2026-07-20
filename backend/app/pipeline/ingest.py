"""Data ingestion: multi-format loading + schema inference.

Supported formats: CSV/TSV, JSON (records or columnar), Excel (xls/xlsx), Parquet.
The loader is intentionally forgiving about encoding and delimiter so users can drop
in messy real-world files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Map file extension -> canonical format label.
EXTENSION_FORMATS: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".txt": "csv",
    ".json": "json",
    ".xlsx": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
    ".pq": "parquet",
}


class UnsupportedFormatError(ValueError):
    """Raised when a file extension is not one we can parse."""


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    fmt = EXTENSION_FORMATS.get(ext)
    if fmt is None:
        raise UnsupportedFormatError(
            f"Unsupported file type '{ext}'. Supported: {sorted(EXTENSION_FORMATS)}"
        )
    return fmt


def _read_csv(path: Path, sep: str | None) -> pd.DataFrame:
    """Read a delimited file, sniffing the separator when not given."""
    read_kwargs: dict[str, Any] = {"sep": sep, "engine": "python"} if sep else {"sep": None, "engine": "python"}
    # Try a couple of common encodings before giving up.
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, **read_kwargs)
        except UnicodeDecodeError:
            continue
    # Last resort: let pandas raise with default encoding.
    return pd.read_csv(path, **read_kwargs)


def _read_json(path: Path) -> pd.DataFrame:
    """Read JSON as records, columnar dict, or line-delimited JSON."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to JSON lines.
        return pd.read_json(path, lines=True)
    if isinstance(data, list):
        return pd.json_normalize(data)
    if isinstance(data, dict):
        # A common shape is {"data": [...]}; unwrap a single list value.
        list_values = [v for v in data.values() if isinstance(v, list)]
        if len(data) == 1 and list_values:
            return pd.json_normalize(list_values[0])
        return pd.json_normalize(data)
    raise ValueError("Unsupported JSON structure for tabular ingestion.")


def load_dataframe(path: str | Path, file_format: str | None = None) -> pd.DataFrame:
    """Load any supported file into a DataFrame."""
    path = Path(path)
    fmt = file_format or detect_format(path.name)

    if fmt == "csv":
        return _read_csv(path, sep=None)
    if fmt == "tsv":
        return _read_csv(path, sep="\t")
    if fmt == "json":
        return _read_json(path)
    if fmt == "excel":
        return pd.read_excel(path)
    if fmt == "parquet":
        return pd.read_parquet(path)
    raise UnsupportedFormatError(f"Unsupported format '{fmt}'.")


def _semantic_type(series: pd.Series) -> str:
    """Classify a column into a semantic role used by later stages."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    # Object/string: try datetime parsing, else decide categorical vs free text.
    non_null = series.dropna()
    if non_null.empty:
        return "categorical"

    sample = non_null.astype(str).head(200)
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    if parsed.notna().mean() > 0.9:
        return "datetime"

    n_unique = series.nunique(dropna=True)
    # Heuristic: many unique long strings => free text; otherwise categorical.
    avg_len = sample.str.len().mean()
    if n_unique > max(50, 0.5 * len(series)) and avg_len and avg_len > 30:
        return "text"
    return "categorical"


def _json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalars to JSON-serialisable Python values."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value) if np.isscalar(value) else False:
        return None
    return value


def infer_schema(df: pd.DataFrame, sample_n: int = 5) -> dict[str, Any]:
    """Build a column-level schema description for the dataset."""
    columns: list[dict[str, Any]] = []
    for name in df.columns:
        series = df[name]
        sample_vals = [_json_safe(v) for v in series.dropna().head(sample_n).tolist()]
        columns.append(
            {
                "name": str(name),
                "dtype": str(series.dtype),
                "semantic": _semantic_type(series),
                "n_missing": int(series.isna().sum()),
                "n_unique": int(series.nunique(dropna=True)),
                "sample": sample_vals,
            }
        )
    return {"columns": columns}


def dataframe_preview(df: pd.DataFrame, n: int) -> list[dict[str, Any]]:
    """Return the first ``n`` rows as JSON-safe dicts."""
    head = df.head(n)
    records: list[dict[str, Any]] = []
    for _, row in head.iterrows():
        records.append({str(k): _json_safe(v) for k, v in row.items()})
    return records
