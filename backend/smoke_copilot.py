"""Smoke test for the Copilot orchestrator (Phase 2) — gate / park / resume.

Drives ``copilot.advance`` with PydanticAI ``TestModel`` (no network/key) over a real
in-memory DB, verifying the state machine:

    profile → [cleaning gate] → approve → clean+EDA → [modeling gate]

It stops at the modeling gate — deliberately *before* training — so it needs neither an
API key nor the ML stack. Cleaning + EDA run for real via the pipeline functions.

    cd backend && python smoke_copilot.py
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pandas as pd
from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents import copilot, providers
from app.db import Base
from app.models import AgentProposal, AgentSession, Dataset, Run, User
from app.pipeline import ingest

# TestModel outputs per agent, matching each agent's output_type schema.
_OUTPUTS = {
    "profiler": {
        "task_type": "classification",
        "target_col": "churned",
        "quality_flags": [],
        "rationale": "churned is a binary target",
    },
    "cleaning": {
        "drop_duplicates": True,
        "impute_numeric": "median",
        "impute_categorical": "mode",
        "drop_constant_columns": True,
        "outlier_method": "none",
        "per_column_reasons": [],
    },
    "modeling": {
        "selected_models": ["Logistic Regression"],
        "test_size": 0.2,
        "cv_strategy": "holdout",
        "rationale": "small dataset — one strong linear baseline",
    },
}


def _fake_get_model(agent_name: str, user=None, db=None) -> TestModel:
    # The modeling agent's list_candidate_models tool imports model_zoo (needs lightgbm,
    # an optional ML dep absent in this smoke env but present in prod) — skip its tools so
    # the state-machine test doesn't depend on the ML stack.
    call_tools = [] if agent_name == "modeling" else "all"
    return TestModel(custom_output_args=_OUTPUTS.get(agent_name), call_tools=call_tools)


def main() -> None:
    from app.config import settings

    settings.ensure_dirs()  # the app's init_db normally does this
    providers.get_model = _fake_get_model  # inject TestModel for every specialist

    df = pd.DataFrame(
        {
            "age": [25, 32, 47, 51, 62, 23, 38, 44, 29, 55, 41, 36],
            "income": [40, 52, 61, 58, 90, 30, 47, 55, 43, 70, 51, 49],
            "churned": [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1],
        }
    )
    tmp = Path(tempfile.mkdtemp()) / "sample.csv"
    df.to_csv(tmp, index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    db.add(User(id=1, email="a@b.co", password_hash="x"))
    ds = Dataset(
        id=1, owner_id=1, filename="sample.csv", path=str(tmp), file_format="csv",
        n_rows=len(df), n_cols=df.shape[1], schema_json=ingest.infer_schema(df),
    )
    db.add(ds)
    session = AgentSession(user_id=1, dataset_id=1, mode="copilot", status="running")
    db.add(session)
    db.commit()

    # 1. Advance → should park at the cleaning gate.
    asyncio.run(copilot.advance(db, session))
    db.refresh(session)
    assert session.status == "awaiting_approval", session.status
    assert session.run_id is not None, "profiling should have created a Run"
    cp = db.query(AgentProposal).filter_by(stage="cleaning").one()
    assert cp.status == "pending"
    print("OK — parked at cleaning gate")
    print(f"   run created (task={db.get(Run, session.run_id).task_type}), cleaning proposal: {cp.proposed_config_json}")

    # 2. Approve cleaning → should run clean+EDA and park at the modeling gate.
    cp.status = "approved"
    session.status = "running"
    db.commit()
    asyncio.run(copilot.advance(db, session))
    db.refresh(session)
    if session.status == "error":
        raise SystemExit(f"copilot errored: {session.error_json}")
    run = db.get(Run, session.run_id)
    assert run.eda_json, "cleaning+EDA should have populated run.eda_json"
    assert session.status == "awaiting_approval", session.status
    mp = db.query(AgentProposal).filter_by(stage="modeling").one()
    print("OK — cleaning+EDA ran, parked at modeling gate")
    print(f"   eda summary keys: {sorted(run.eda_json.get('summary', {}).keys())[:5]}")
    print(f"   modeling proposal: {mp.proposed_config_json.get('selected_models')}")
    print("Copilot state machine verified through both gates.")


if __name__ == "__main__":
    main()
