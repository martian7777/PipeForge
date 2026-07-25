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


# --- Agentic AI layer -------------------------------------------------------
# These tables are additive; the classic pipeline never touches them. See
# app/agents/ and docs/ROADMAP.md.


class AgentSession(Base):
    """One agentic interaction over a dataset/run (advise, chat, copilot, autopilot)."""

    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    dataset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("runs.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="advise")  # advise|chat|copilot|autopilot
    status: Mapped[str] = mapped_column(String(32), default="running")  # running|awaiting_approval|done|error
    current_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # drives the live UI
    error_json: Mapped[dict[str, Any]] = mapped_column("error", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="AgentMessage.id"
    )


class AgentMessage(Base):
    """One step in a session: a model turn, a tool call, or an error.

    The full decision/conversation trace, and the source the UI derives per-agent
    status from.
    """

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("agent_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # system|user|assistant|tool|error
    agent_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tool_args_json: Mapped[dict[str, Any]] = mapped_column("tool_args", JSON, default=dict)
    tool_result_json: Mapped[dict[str, Any]] = mapped_column("tool_result", JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="done")  # running|done|error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["AgentSession"] = relationship(back_populates="messages")


class AgentProposal(Base):
    """A Copilot approval gate: a stage config the agent proposes before executing it."""

    __tablename__ = "agent_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("agent_sessions.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))  # cleaning|modeling|...
    proposed_config_json: Mapped[dict[str, Any]] = mapped_column("proposed_config", JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|rejected|edited
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AgentConfig(Base):
    """Per-user model override for one agent. Falls back to the system default (config.py)."""

    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
