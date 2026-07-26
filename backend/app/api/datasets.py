"""Dataset endpoints: upload, list, detail, preview, and task detection.

All routes require authentication and are scoped to the current user.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..db import get_db
from ..models import Dataset, User
from ..pipeline import detect, ingest
from ..ratelimit import limiter
from ..schemas import (
    ColumnSchema,
    DatasetDetail,
    DatasetOut,
    DetectOut,
    PreviewOut,
)
from ..security import current_user
from ..storage import new_object_key, upload_path

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _get_owned_dataset_or_404(db: Session, dataset_id: int, user: User) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.owner_id != user.id:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return ds


@router.post("", response_model=DatasetDetail)
@limiter.limit(settings.ratelimit_upload)
def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Dataset:
    """Accept a data file, persist it (sharded), infer its schema, record metadata."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    try:
        file_format = ingest.detect_format(file.filename)
    except ingest.UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    key = new_object_key(file.filename)
    dest = upload_path(key)

    size = 0
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds maximum upload size.")
            out.write(chunk)

    try:
        df = ingest.load_dataframe(dest, file_format)
    except Exception as exc:  # noqa: BLE001 - surface parse errors to the client
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}") from exc

    schema = ingest.infer_schema(df)
    ds = Dataset(
        owner_id=user.id,
        filename=file.filename,
        path=str(dest),
        file_format=file_format,
        n_rows=int(df.shape[0]),
        n_cols=int(df.shape[1]),
        schema_json=schema,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)

    audit.record(
        db,
        audit.DATASET_UPLOADED,
        request=request,
        actor=user,
        target=f"dataset:{ds.id}",
        filename=file.filename,
        size_bytes=size,
        n_rows=ds.n_rows,
        n_cols=ds.n_cols,
    )
    return ds


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[Dataset]:
    return list(
        db.scalars(
            select(Dataset).where(Dataset.owner_id == user.id).order_by(Dataset.created_at.desc())
        )
    )


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(
    dataset_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Dataset:
    return _get_owned_dataset_or_404(db, dataset_id, user)


@router.get("/{dataset_id}/preview", response_model=PreviewOut)
def preview_dataset(
    dataset_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> PreviewOut:
    ds = _get_owned_dataset_or_404(db, dataset_id, user)
    df = ingest.load_dataframe(ds.path, ds.file_format)
    rows = ingest.dataframe_preview(df, settings.preview_rows)
    columns = [ColumnSchema(**c) for c in ds.schema_json.get("columns", [])]
    return PreviewOut(columns=columns, rows=rows, n_rows=ds.n_rows, n_cols=ds.n_cols)


@router.post("/{dataset_id}/detect", response_model=DetectOut)
def detect_task(
    dataset_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> DetectOut:
    ds = _get_owned_dataset_or_404(db, dataset_id, user)
    return DetectOut(**detect.suggest(ds.schema_json, ds.n_rows))


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    ds = _get_owned_dataset_or_404(db, dataset_id, user)
    filename = ds.filename
    Path(ds.path).unlink(missing_ok=True)
    db.delete(ds)
    db.commit()
    audit.record(
        db,
        audit.DATASET_DELETED,
        request=request,
        actor=user,
        target=f"dataset:{dataset_id}",
        filename=filename,
    )
