"""Run endpoints: create a pipeline run (clean + EDA now; training in Milestone 3),
poll status, and fetch EDA results + the HTML report.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Dataset, Run, User
from ..pipeline import clean, eda, ingest
from ..schemas import ChartSpec, EdaOut, RunCreate, RunOut, RunStatus
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
        status="running",
        stage="cleaning",
        progress=10.0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Milestone 2 runs the cleaning + EDA stages synchronously. Milestone 3 moves the
    # heavy training work onto the ProcessPoolExecutor job runner.
    try:
        df = ingest.load_dataframe(ds.path, ds.file_format)
        cleaned, clean_report = clean.clean_dataframe(df, body.cleaning.model_dump())
        run.stage = "eda"
        run.progress = 60.0
        db.commit()

        report_key = f"{uuid.uuid4().hex}.html"
        report_path = settings.reports_dir / report_key
        eda_payload = eda.run_eda(cleaned, run.task_type, run.target_col, report_path)
        eda_payload["clean_report"] = clean_report

        run.eda_json = eda_payload
        run.report_path = str(report_path)
        run.stage = "done"
        run.progress = 100.0
        run.status = "done"
        run.message = "EDA complete. Model training available in Milestone 3."
    except Exception as exc:  # noqa: BLE001
        run.status = "error"
        run.stage = "error"
        run.message = str(exc)
    db.commit()
    db.refresh(run)
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
        raise HTTPException(status_code=409, detail="EDA not available for this run")
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
