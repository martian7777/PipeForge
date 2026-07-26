"""Background pipeline job runner.

Runs the full pipeline (clean -> EDA -> train -> evaluate -> persist) off the request
path in a thread pool, writing stage/progress back to the Run row so the frontend can
poll ``/api/runs/{id}/status``. This keeps the API responsive during long training jobs.

At fleet scale the in-process pool is swapped for a shared queue (Redis/RQ or Celery)
so training workers scale independently of the API â€” see docs/ROADMAP.md.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import settings
from ..db import SessionLocal
from ..models import AgentSession, Dataset, ModelResult, Run
from ..pipeline import clean, eda, ingest

# ``train``/``registry`` pull the ML stack (sklearn/xgboost/joblib); import them lazily
# inside ``train_and_persist`` so merely importing the runner (e.g. from the API to submit
# a job) doesn't require the ML libraries — only the worker that trains does.

_executor = ThreadPoolExecutor(max_workers=settings.job_max_workers, thread_name_prefix="pipeforge-job")

# Task types that go through model training (Milestone 3). Others stop after EDA.
TRAINABLE = {"classification", "regression"}


def submit_run(run_id: int) -> None:
    """Schedule a run for background execution."""
    _executor.submit(_safe_execute, run_id)


def _safe_execute(run_id: int) -> None:
    try:
        execute_run(run_id)
    except Exception:  # noqa: BLE001 - last-resort guard; execute_run records its own errors
        import traceback

        traceback.print_exc()


def _set(db, run: Run, *, stage: str | None = None, progress: float | None = None,
         status: str | None = None, message: str | None = None) -> None:
    if stage is not None:
        run.stage = stage
    if progress is not None:
        run.progress = round(progress, 1)
    if status is not None:
        run.status = status
    if message is not None:
        run.message = message
    db.commit()


def execute_run(run_id: int) -> None:
    """Execute the pipeline for a run. Runs in a worker thread with its own DB session."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return
        ds = db.get(Dataset, run.dataset_id)
        if ds is None:
            _set(db, run, status="error", stage="error", message="Dataset missing")
            return

        _set(db, run, status="running", stage="loading", progress=5)
        df = ingest.load_dataframe(ds.path, ds.file_format)

        # 1. Clean.
        _set(db, run, stage="cleaning", progress=12)
        cleaning_cfg = run.config_json.get("cleaning", {})
        cleaned, clean_report = clean.clean_dataframe(df, cleaning_cfg)

        # 2. EDA.
        _set(db, run, stage="eda", progress=25)
        report_path = settings.reports_dir / f"{uuid.uuid4().hex}.html"
        eda_payload = eda.run_eda(cleaned, run.task_type, run.target_col, report_path)
        eda_payload["clean_report"] = clean_report
        run.eda_json = eda_payload
        run.report_path = str(report_path)
        db.commit()

        # 3. Train (supervised tabular only in Milestone 3).
        if run.task_type in TRAINABLE and run.target_col:
            _set(db, run, stage="training", progress=30)

            def progress_cb(frac: float, msg: str) -> None:
                _set(db, run, stage="training", progress=30 + frac * 60, message=msg)

            message = train_and_persist(db, run, cleaned, progress_cb=progress_cb)
            _set(db, run, status="done", stage="done", progress=100, message=message)
        else:
            _set(
                db, run, status="done", stage="done", progress=100,
                message="Cleaning + EDA complete (no model training for this task type).",
            )
    except Exception as exc:  # noqa: BLE001
        try:
            run = db.get(Run, run_id)
            if run is not None:
                _set(db, run, status="error", stage="error", message=str(exc))
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


def train_and_persist(db, run: Run, df, *, model_names=None, test_size: float = 0.2, progress_cb=None) -> str:
    """Train (optionally a model subset), persist the leaderboard + best artifact.

    Shared by the classic runner and the Copilot orchestrator. Sets ``run.best_model_id``
    and returns a human-readable "Best model: …" summary; the caller owns run status.
    """
    from ..pipeline import registry, train  # lazy: ML stack loaded only when training

    result = train.train_models(
        df, run.target_col, run.task_type, progress_cb, test_size=test_size, model_names=model_names
    )
    feature_columns = (
        result.feature_spec["numeric"]
        + result.feature_spec["categorical"]
        + result.feature_spec["datetime"]
    )
    best_id: int | None = None
    for m in result.models:
        artifact_key = None
        if m.rank == 1 and not m.error:
            artifact_key = registry.save_model(
                m.pipeline, run.task_type, run.target_col, feature_columns, result.classes
            )
        mr = ModelResult(
            run_id=run.id,
            model_name=m.name,
            family=m.family,
            metrics_json=m.metrics,
            plots_json=m.plots,
            artifact_path=artifact_key,
            rank=m.rank if not m.error else 999,
        )
        db.add(mr)
        db.flush()
        if m.rank == 1 and not m.error:
            best_id = mr.id
    run.best_model_id = best_id
    db.commit()

    best = next((m for m in result.models if m.rank == 1), None)
    score = f"{result.primary_metric}={best.metrics.get(result.primary_metric):.4g}" if best else ""
    return f"Best model: {best.name if best else '?'} ({score})"


# --- Copilot background driver -------------------------------------------------------
# Runs the async orchestrator in a worker thread (its own event loop + DB session),
# parking at approval gates. Re-submitted by the /approve endpoint to resume.


def submit_copilot(session_id: int) -> None:
    """Schedule (or resume) a copilot session on the background pool."""
    _executor.submit(_safe_copilot, session_id)


def _safe_copilot(session_id: int) -> None:
    import asyncio

    from ..agents import copilot

    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if session is None:
            return
        asyncio.run(copilot.advance(db, session))
    except Exception:  # noqa: BLE001 - copilot.advance records its own errors; last-resort guard
        import traceback

        traceback.print_exc()
    finally:
        db.close()
