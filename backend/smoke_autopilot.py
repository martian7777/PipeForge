"""Smoke test for Autopilot (Phase 3) — the Forge Master runs end-to-end, no gates.

Drives ``copilot.advance`` for an ``autopilot`` session with PydanticAI ``TestModel``
(no network/key) over a real in-memory DB. Both gates auto-approve; cleaning + EDA run
for real; training is stubbed (the ML stack is absent in this smoke env but the real path
reuses the proven ``runner.train_and_persist``). Verifies the whole flow reaches ``done``
with a critic verdict.

    cd backend && python smoke_autopilot.py
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pandas as pd
from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import copilot, providers
from app.db import Base
from app.jobs import runner
from app.models import AgentSession, Dataset, ModelResult, Run, User
from app.pipeline import ingest

_OUTPUTS = {
    "profiler": {"task_type": "classification", "target_col": "churned", "quality_flags": [], "rationale": "binary target"},
    "cleaning": {
        "drop_duplicates": True, "impute_numeric": "median", "impute_categorical": "mode",
        "drop_constant_columns": True, "outlier_method": "none", "per_column_reasons": [],
    },
    "modeling": {"selected_models": ["Logistic Regression"], "test_size": 0.2, "cv_strategy": "holdout", "rationale": "baseline"},
    "critic": {"recommended_model_id": None, "warnings": [], "justification": "Logistic Regression is the strongest baseline."},
}


def _fake_get_model(agent_name: str, user=None, db=None) -> TestModel:
    call_tools = [] if agent_name == "modeling" else "all"
    return TestModel(custom_output_args=_OUTPUTS.get(agent_name), call_tools=call_tools)


def _fake_train(db, run, df, *, model_names=None, test_size=0.2, progress_cb=None) -> str:
    # Stand in for the real ML training: persist one leaderboard row + best model.
    mr = ModelResult(run_id=run.id, model_name="Logistic Regression", family="linear",
                     metrics_json={"f1_weighted": 0.87}, plots_json={}, rank=1)
    db.add(mr)
    db.flush()
    run.best_model_id = mr.id
    db.commit()
    return "Best model: Logistic Regression (f1_weighted=0.87)"


def main() -> None:
    from app.config import settings

    settings.ensure_dirs()
    providers.get_model = _fake_get_model
    runner.train_and_persist = _fake_train  # copilot imports runner lazily, so patch here

    df = pd.DataFrame(
        {
            "age": [25, 32, 47, 51, 62, 23, 38, 44, 29, 55, 41, 36],
            "income": [40, 52, 61, 58, 90, 30, 47, 55, 43, 70, 51, 49],
            "churned": [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1],
        }
    )
    tmp = Path(tempfile.mkdtemp()) / "sample.csv"
    df.to_csv(tmp, index=False)

    # Mirror production db.py: check_same_thread=False + a shared pool so PydanticAI's
    # threaded sync-tool execution can use the same in-memory connection.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(User(id=1, email="a@b.co", password_hash="x"))
    db.add(Dataset(id=1, owner_id=1, filename="sample.csv", path=str(tmp), file_format="csv",
                   n_rows=len(df), n_cols=df.shape[1], schema_json=ingest.infer_schema(df)))
    session = AgentSession(user_id=1, dataset_id=1, mode="autopilot", status="running")
    db.add(session)
    db.commit()

    asyncio.run(copilot.advance(db, session))
    db.refresh(session)
    if session.status == "error":
        raise SystemExit(f"autopilot errored: {session.error_json}")

    run = db.get(Run, session.run_id)
    assert session.status == "done", session.status
    assert run.eda_json, "cleaning+EDA should have run"
    assert run.best_model_id is not None, "training should have produced a best model"
    agents_seen = sorted({m.agent_name for m in session.messages if m.agent_name})
    assert "critic" in agents_seen, agents_seen

    print("OK — Autopilot ran end-to-end with no gates")
    print(f"   agents involved: {agents_seen}")
    print(f"   status: {session.status}, best_model_id: {run.best_model_id}")
    print(f"   final note: {session.messages[-1].content!r}")


if __name__ == "__main__":
    main()
