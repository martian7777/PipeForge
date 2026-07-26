"""Copilot orchestrator — an approval-gated state machine over the real pipeline.

Unlike Advise/Chat (read-only, request-response), Copilot *drives* the pipeline with two
human-in-the-loop gates. It is resumable: ``advance()`` inspects DB state and continues
from wherever it last stopped, so the background runner can park at a gate
(``awaiting_approval``) and pick up again when the user approves.

Stages:  profile → [cleaning gate] → clean+EDA → [modeling gate] → train → critique → done

The specialist agents only *propose* typed plans; this module executes them via the
tested ``pipeline/*`` functions after approval. Heavy ML imports (train/registry) are
lazy so the profiling/cleaning stages don't require the ML stack.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AgentMessage, AgentProposal, AgentSession, Dataset, Run, User
from ..pipeline import clean, eda
from ..schemas import CleaningConfig
from . import providers
from .deps import AgentDeps
from .specialists import (
    build_cleaning_agent,
    build_critic,
    build_modeling_strategist,
    build_profiler,
)

TRAINABLE = {"classification", "regression"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _msg(db: Session, session: AgentSession, **kw: Any) -> None:
    db.add(AgentMessage(session_id=session.id, **kw))
    db.commit()


def _proposal(db: Session, session: AgentSession, stage: str) -> Optional[AgentProposal]:
    return (
        db.query(AgentProposal)
        .filter(AgentProposal.session_id == session.id, AgentProposal.stage == stage)
        .order_by(AgentProposal.id.desc())
        .first()
    )


def _deps(db: Session, session: AgentSession, run: Optional[Run]) -> AgentDeps:
    user = db.get(User, session.user_id)
    dataset = db.get(Dataset, run.dataset_id if run else session.dataset_id)
    if dataset is None:
        raise ValueError("Copilot session has no resolvable dataset")
    return AgentDeps(db=db, user=user, dataset=dataset, run=run)


def _has_results(db: Session, run: Run) -> bool:
    from ..models import ModelResult

    return db.query(ModelResult).filter(ModelResult.run_id == run.id).count() > 0


async def advance(db: Session, session: AgentSession) -> None:
    """Drive the copilot flow forward until it parks at a gate, finishes, or errors."""
    try:
        await _advance(db, session)
    except Exception as exc:  # noqa: BLE001 - surface to the UI, never crash the worker
        db.rollback()
        session = db.get(AgentSession, session.id)
        if session is not None:
            session.status = "error"
            session.current_agent = None
            session.error_json = {"message": str(exc)}
            _msg(db, session, role="error", content=str(exc), status="error")


async def _advance(db: Session, session: AgentSession) -> None:
    # 1. Profile → create the Run.
    if session.run_id is None:
        session.status = "running"
        session.current_agent = "profiler"
        db.commit()
        deps = _deps(db, session, None)
        profiler = build_profiler(providers.get_model("profiler", deps.user, db))
        report = (await profiler.run("Profile this dataset.", deps=deps)).output
        _msg(db, session, role="assistant", agent_name="profiler", content=report.rationale,
             tool_result_json=report.model_dump())
        run = Run(
            dataset_id=session.dataset_id,
            task_type=report.task_type,
            target_col=report.target_col,
            config_json={"agent_mode": "copilot"},
            status="running",
            stage="profiling",
            progress=10.0,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        session.run_id = run.id
        db.commit()

    run = db.get(Run, session.run_id)

    # 2. Cleaning gate.
    cp = _proposal(db, session, "cleaning")
    if cp is None:
        session.current_agent = "cleaning"
        db.commit()
        deps = _deps(db, session, run)
        agent = build_cleaning_agent(providers.get_model("cleaning", deps.user, db))
        plan = (await agent.run("Propose a cleaning strategy for this dataset.", deps=deps)).output
        cfg = CleaningConfig(**plan.model_dump(exclude={"per_column_reasons"})).model_dump()
        db.add(AgentProposal(session_id=session.id, stage="cleaning", proposed_config_json=cfg))
        reasons = "\n".join(f"• {r.column}: {r.action} — {r.reason}" for r in plan.per_column_reasons)
        _msg(db, session, role="assistant", agent_name="cleaning",
             content=reasons or "Proposed a cleaning configuration.")
        return _park(db, session)
    if cp.status == "pending":
        return _park(db, session)
    if cp.status == "rejected":
        return _finish(db, session, "Cleaning rejected — stopped.")

    # 3. Execute cleaning + EDA (once).
    if not run.eda_json:
        session.current_agent = None
        session.status = "running"
        run.stage = "cleaning"
        db.commit()
        deps = _deps(db, session, run)
        df = deps.dataframe()
        cleaned, clean_report = clean.clean_dataframe(df, cp.proposed_config_json)
        report_path = settings.reports_dir / f"{uuid.uuid4().hex}.html"
        payload = eda.run_eda(cleaned, run.task_type, run.target_col, report_path)
        payload["clean_report"] = clean_report
        run.eda_json = payload
        run.report_path = str(report_path)
        run.stage = "eda"
        run.progress = 45.0
        db.commit()
        _msg(db, session, role="tool", agent_name="cleaning", tool_name="run_cleaning")

    # Non-trainable task types finish after EDA.
    if run.task_type not in TRAINABLE or not run.target_col:
        run.status = "done"
        db.commit()
        return _finish(db, session, "Cleaning + EDA complete (no training for this task type).")

    # 4. Modeling gate.
    mp = _proposal(db, session, "modeling")
    if mp is None:
        session.current_agent = "modeling"
        db.commit()
        deps = _deps(db, session, run)
        agent = build_modeling_strategist(providers.get_model("modeling", deps.user, db))
        plan = (await agent.run("Propose which models to train and the split.", deps=deps)).output
        db.add(AgentProposal(session_id=session.id, stage="modeling", proposed_config_json=plan.model_dump()))
        _msg(db, session, role="assistant", agent_name="modeling", content=plan.rationale,
             tool_result_json=plan.model_dump())
        return _park(db, session)
    if mp.status == "pending":
        return _park(db, session)
    if mp.status == "rejected":
        return _finish(db, session, "Modeling rejected — stopped after EDA.")

    # 5. Execute training (once).
    if run.best_model_id is None and not _has_results(db, run):
        _execute_training(db, session, run, cp.proposed_config_json, mp.proposed_config_json)

    # 6. Critique.
    session.current_agent = "critic"
    db.commit()
    deps = _deps(db, session, run)
    critic = build_critic(providers.get_model("critic", deps.user, db))
    verdict = (await critic.run("Interpret the leaderboard and recommend a model.", deps=deps)).output
    warn = "\n".join(f"⚠ {w}" for w in verdict.warnings)
    _msg(db, session, role="assistant", agent_name="critic",
         content=(verdict.justification + ("\n" + warn if warn else "")),
         tool_result_json=verdict.model_dump())
    return _finish(db, session, "Run complete.")


def _execute_training(
    db: Session, session: AgentSession, run: Run, cleaning_cfg: dict, plan: dict
) -> None:
    """Clean deterministically, train the approved model subset, persist the leaderboard."""
    from ..jobs import runner  # lazy: pulls the ML stack (train/registry) only here

    session.current_agent = "modeling"
    run.stage = "training"
    run.progress = 60.0
    db.commit()

    deps = _deps(db, session, run)
    cleaned, _ = clean.clean_dataframe(deps.dataframe(), cleaning_cfg)
    result = runner.train_and_persist(
        db,
        run,
        cleaned,
        model_names=plan.get("selected_models") or None,
        test_size=float(plan.get("test_size", 0.2)),
    )
    _msg(db, session, role="tool", agent_name="modeling", tool_name="run_training",
         tool_result_json={"best": result})


# --- terminal / pause helpers ---


def _park(db: Session, session: AgentSession) -> None:
    session.status = "awaiting_approval"
    db.commit()


def _finish(db: Session, session: AgentSession, note: str) -> None:
    session.status = "done"
    session.current_agent = None
    db.commit()
    _msg(db, session, role="assistant", agent_name="orchestrator", content=note)
