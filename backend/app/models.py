"""SQLAlchemy ORM models: Dataset, Run, ModelResult, Job."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A registered user. Owns datasets and runs."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Dataset(Base):
    """An uploaded data file plus its inferred schema."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(String(1024))
    file_format: Mapped[str] = mapped_column(String(32))
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    n_cols: Mapped[int] = mapped_column(Integer, default=0)
    # {"columns": [{"name","dtype","semantic","n_missing","n_unique","sample"}...]}
    schema_json: Mapped[dict[str, Any]] = mapped_column("schema", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="datasets")
    runs: Mapped[list["Run"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class Run(Base):
    """A single pipeline execution over a dataset."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    task_type: Mapped[str] = mapped_column(String(32))  # regression|classification|timeseries|clustering
    target_col: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column("config", JSON, default=dict)

    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued|running|done|error
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    best_model_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eda_json: Mapped[dict[str, Any]] = mapped_column("eda", JSON, default=dict)
    report_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="runs")
    results: Mapped[list["ModelResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ModelResult(Base):
    """One trained candidate model in a run's leaderboard."""

    __tablename__ = "model_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    model_name: Mapped[str] = mapped_column(String(128))
    family: Mapped[str] = mapped_column(String(64))  # linear|tree|boosting|deep|classical_ts
    metrics_json: Mapped[dict[str, Any]] = mapped_column("metrics", JSON, default=dict)
    plots_json: Mapped[dict[str, Any]] = mapped_column("plots", JSON, default=dict)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped["Run"] = relationship(back_populates="results")
