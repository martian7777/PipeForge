"""Smoke test for the agentic AI layer — mirrors smoke_test.py / smoke_train.py.

Runs the EDA Analyst end-to-end with PydanticAI's ``TestModel`` (no network, no API key):
the test model calls every tool and returns a schema-valid ``EdaNarrative``. This exercises
the real reuse path — the tools call the actual ``pipeline/*`` functions over a real
DataFrame — and proves the typed output contract holds.

    cd backend && python smoke_agent.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from pydantic_ai.models.test import TestModel

from app.agents.deps import AgentDeps
from app.agents.schemas import EdaNarrative
from app.agents.specialists import build_eda_analyst
from app.models import Dataset
from app.pipeline import ingest


def main() -> None:
    # 1. A tiny but realistic dataset.
    df = pd.DataFrame(
        {
            "age": [25, 32, 47, 51, 62, 23, 38, 44],
            "income": [40000, 52000, 61000, 58000, 90000, 30000, 47000, 55000],
            "city": ["NY", "LA", "NY", "SF", "SF", "LA", "NY", "SF"],
            "churned": [0, 1, 0, 0, 1, 1, 0, 1],
        }
    )
    tmp = Path(tempfile.mkdtemp()) / "sample.csv"
    df.to_csv(tmp, index=False)

    schema = ingest.infer_schema(df)
    dataset = Dataset(
        id=1,
        owner_id=1,
        filename="sample.csv",
        path=str(tmp),
        file_format="csv",
        n_rows=len(df),
        n_cols=df.shape[1],
        schema_json=schema,
    )

    # 2. Run the EDA Analyst with TestModel (calls tools, returns a valid EdaNarrative).
    deps = AgentDeps(db=None, user=None, dataset=dataset, run=None)
    agent = build_eda_analyst(TestModel())
    result = agent.run_sync(
        "Analyse this dataset and its EDA. Report insights, risks, and hypotheses.",
        deps=deps,
    )

    assert isinstance(result.output, EdaNarrative), type(result.output)
    tool_calls = [
        p.tool_name
        for m in result.all_messages()
        for p in getattr(m, "parts", [])
        if getattr(p, "part_kind", "") == "tool-call"
    ]
    print("OK — agent layer wired up")
    print(f"   tools invoked: {tool_calls}")
    print(f"   output type:   {type(result.output).__name__}")
    print(f"   summary:       {result.output.summary[:80]!r}")


if __name__ == "__main__":
    main()
