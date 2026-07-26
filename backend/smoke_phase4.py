"""Smoke test for Phase 4 — hyperparameter tuning + explainability.

Verifies (no network/key, no ML stack):
1. ``explain.top_drivers`` reads stored attributions.
2. The ``read_feature_importance`` tool returns a model's drivers from ``plots_json``.
3. Autopilot forwards the Modeling Strategist's ``tune`` + ``hyperparameters`` into
   ``train_and_persist``, and the Critic surfaces ``key_drivers``.

The actual randomized search + SHAP run only with the ML stack installed; here training is
stubbed (as in the Phase 3 smoke) and we assert the wiring around it.

    cd backend && python smoke_phase4.py
"""
from __future__ import annotations

import asyncio
import tempfile
import types
from pathlib import Path

import pandas as pd
from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import copilot, providers
from app.agents.deps import AgentDeps
from app.agents.tools import read_feature_importance
from app.db import Base
from app.jobs import runner
from app.models import AgentSession, Dataset, ModelResult, Run, User
from app.pipeline import explain, ingest

_IMPORTANCE = {"method": "coef", "features": ["income", "age"], "importance": [0.7, 0.3]}

_OUTPUTS = {
    "profiler": {"task_type": "classification", "target_col": "churned", "quality_flags": [], "rationale": "binary"},
    "cleaning": {
        "drop_duplicates": True, "impute_numeric": "median", "impute_categorical": "mode",
        "drop_constant_columns": True, "outlier_method": "none", "per_column_reasons": [],
    },
    "modeling": {
        "selected_models": ["Logistic Regression"], "test_size": 0.2, "cv_strategy": "holdout",
        "tune": True, "hyperparameters": {"Logistic Regression": {"C": [0.1, 1.0]}},
        "rationale": "tune C",
    },
    "critic": {"recommended_model_id": None, "warnings": [], "key_drivers": ["income", "age"], "justification": "income drives it"},
}

_captured: dict = {}


def _fake_get_model(agent_name: str, user=None, db=None) -> TestModel:
    call_tools = [] if agent_name == "modeling" else "all"
    return TestModel(custom_output_args=_OUTPUTS.get(agent_name), call_tools=call_tools)


def _fake_train(db, run, df, *, model_names=None, test_size=0.2, hyperparameters=None, tune=False, progress_cb=None) -> str:
    _captured.update(tune=tune, hyperparameters=hyperparameters, model_names=model_names)
    mr = ModelResult(run_id=run.id, model_name="Logistic Regression", family="linear",
                     metrics_json={"f1_weighted": 0.9}, plots_json={"feature_importance": _IMPORTANCE}, rank=1)
    db.add(mr)
    db.flush()
    run.best_model_id = mr.id
    db.commit()
    return "Best model: Logistic Regression (f1_weighted=0.9)"


def main() -> None:
    from app.config import settings

    settings.ensure_dirs()

    # 1. Pure explainability helper.
    assert explain.top_drivers({"feature_importance": _IMPORTANCE}) == ["income", "age"]
    assert explain.top_drivers({"shap": {"features": ["x"], "importance": [1.0]}}) == ["x"]
    print("OK — explain.top_drivers reads SHAP/importance")

    providers.get_model = _fake_get_model
    runner.train_and_persist = _fake_train

    df = pd.DataFrame({
        "age": [25, 32, 47, 51, 62, 23, 38, 44, 29, 55, 41, 36],
        "income": [40, 52, 61, 58, 90, 30, 47, 55, 43, 70, 51, 49],
        "churned": [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1],
    })
    tmp = Path(tempfile.mkdtemp()) / "sample.csv"
    df.to_csv(tmp, index=False)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(User(id=1, email="a@b.co", password_hash="x"))
    db.add(Dataset(id=1, owner_id=1, filename="s.csv", path=str(tmp), file_format="csv",
                   n_rows=len(df), n_cols=df.shape[1], schema_json=ingest.infer_schema(df)))
    session = AgentSession(user_id=1, dataset_id=1, mode="autopilot", status="running")
    db.add(session)
    db.commit()

    asyncio.run(copilot.advance(db, session))
    db.refresh(session)
    if session.status == "error":
        raise SystemExit(f"phase4 errored: {session.error_json}")

    # 2. Hyperparameters + tune were forwarded to training.
    assert _captured.get("tune") is True, _captured
    assert _captured.get("hyperparameters") == {"Logistic Regression": {"C": [0.1, 1.0]}}, _captured
    print(f"OK — tune + hyperparameters forwarded: {_captured['hyperparameters']}")

    # 3. The explainability tool returns the model's drivers.
    run = db.get(Run, session.run_id)
    ctx = types.SimpleNamespace(deps=AgentDeps(db=db, user=None, dataset=None, run=run))
    fi = read_feature_importance(ctx, run.best_model_id)
    assert fi["top_drivers"] == ["income", "age"], fi
    print(f"OK — read_feature_importance drivers: {fi['top_drivers']} (method={fi['method']})")

    # 4. The critic surfaced key_drivers in its message.
    critic_msg = next(m for m in reversed(session.messages) if m.agent_name == "critic")
    assert "Key drivers: income, age" in (critic_msg.content or ""), critic_msg.content
    print("OK — Critic reported key drivers")
    print("Phase 4 (hyperparameter tuning + explainability) verified.")


if __name__ == "__main__":
    main()
