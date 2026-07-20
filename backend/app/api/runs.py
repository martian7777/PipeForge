"""Run endpoints: create a pipeline run (async), poll status, fetch EDA, leaderboard,
model details, artifact download, and prediction on new data.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import runner
from ..models import Dataset, ModelResult, Run, User
from ..pipeline import evaluate, ingest, registry
from ..schemas import (
    ChartSpec,
    EdaOut,
    LeaderboardOut,
    ModelResultDetail,
    ModelResultOut,
    PredictionOut,
    RunCreate,
    RunOut,
    RunStatus,
)
from ..security import current_user

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _get_owned_run_or_404(db: Session, run_id: int, user: User) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    ds = db.get(Dataset, run.dataset_id)
    if ds is None or ds.owner_id != user.id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.post("", response_model=RunOut, status_code=201)
def create_run(
    body: RunCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Run:
    ds = db.get(Dataset, body.dataset_id)
    if ds is None or ds.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if body.target_col and body.target_col not in [
        c["name"] for c in ds.schema_json.get("columns", [])
    ]:
        raise HTTPException(status_code=422, detail="target_col not present in dataset")

    run = Run(
        dataset_id=ds.id,
        task_type=body.task_type.value,
        target_col=body.target_col,
        config_json={"cleaning": body.cleaning.model_dump()},
        status="queued",
        stage="queued",
        progress=0.0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Hand off to the background job runner; the client polls /status.
    runner.submit_run(run.id)
    return run


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Run]:
    owned_ids = select(Dataset.id).where(Dataset.owner_id == user.id)
    return list(
        db.scalars(select(Run).where(Run.dataset_id.in_(owned_ids)).order_by(Run.created_at.desc()))
    )


@router.get("/{run_id}/status", response_model=RunStatus)
def run_status(
    run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Run:
    return _get_owned_run_or_404(db, run_id, user)


@router.get("/{run_id}/eda", response_model=EdaOut)
def run_eda_result(
    run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> EdaOut:
    run = _get_owned_run_or_404(db, run_id, user)
    if not run.eda_json:
        raise HTTPException(status_code=409, detail="EDA not available yet")
    report_url = f"/api/runs/{run_id}/report" if run.report_path else None
    charts = [ChartSpec(**c) for c in run.eda_json.get("charts", [])]
    return EdaOut(summary=run.eda_json.get("summary", {}), charts=charts, report_url=report_url)


@router.get("/{run_id}/report")
def run_report(
    run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> FileResponse:
    run = _get_owned_run_or_404(db, run_id, user)
    if not run.report_path or not Path(run.report_path).exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(run.report_path, media_type="text/html")


@router.get("/{run_id}/leaderboard", response_model=LeaderboardOut)
def leaderboard(
    run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> LeaderboardOut:
    run = _get_owned_run_or_404(db, run_id, user)
    results = list(
        db.scalars(select(ModelResult).where(ModelResult.run_id == run.id).order_by(ModelResult.rank))
    )
    metric = evaluate.primary_metric(run.task_type)[0] if run.task_type in ("classification", "regression") else None
    models = [
        ModelResultOut(
            id=r.id,
            model_name=r.model_name,
            family=r.family,
            metrics_json=r.metrics_json,
            rank=r.rank,
            has_artifact=bool(r.artifact_path),
        )
        for r in results
    ]
    return LeaderboardOut(primary_metric=metric, best_model_id=run.best_model_id, models=models)


@router.get("/{run_id}/models/{model_id}", response_model=ModelResultDetail)
def model_detail(
    run_id: int, model_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> ModelResultDetail:
    run = _get_owned_run_or_404(db, run_id, user)
    mr = db.get(ModelResult, model_id)
    if mr is None or mr.run_id != run.id:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelResultDetail(
        id=mr.id,
        model_name=mr.model_name,
        family=mr.family,
        metrics_json=mr.metrics_json,
        rank=mr.rank,
        has_artifact=bool(mr.artifact_path),
        plots_json=mr.plots_json,
    )


@router.get("/{run_id}/models/{model_id}/download")
def download_model(
    run_id: int, model_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> FileResponse:
    run = _get_owned_run_or_404(db, run_id, user)
    mr = db.get(ModelResult, model_id)
    if mr is None or mr.run_id != run.id or not mr.artifact_path:
        raise HTTPException(status_code=404, detail="Model artifact not available")
    path = registry.artifact_file(mr.artifact_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"{mr.model_name.replace(' ', '_')}.joblib",
    )


@router.post("/{run_id}/predict", response_model=PredictionOut)
async def predict(
    run_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PredictionOut:
    """Predict on newly uploaded rows using the run's best model."""
    run = _get_owned_run_or_404(db, run_id, user)
    if not run.best_model_id:
        raise HTTPException(status_code=409, detail="No trained model available for this run")
    mr = db.get(ModelResult, run.best_model_id)
    if mr is None or not mr.artifact_path:
        raise HTTPException(status_code=409, detail="Best model artifact missing")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    try:
        fmt = ingest.detect_format(file.filename)
    except ingest.UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    # Persist the uploaded rows to a temp file so the same multi-format loader applies.
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tf:
        tf.write(content)
        tmp_path = tf.name
    try:
        df = ingest.load_dataframe(tmp_path, fmt)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    try:
        result = registry.predict(mr.artifact_path, df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    preds = result["predictions"]
    return PredictionOut(predictions=preds, n=len(preds))
