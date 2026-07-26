"""Pydantic request/response schemas for the API layer.

Request models are strict (``extra="forbid"``) and use enums + field constraints so
malformed input is rejected at the boundary before touching business logic.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class TaskType(str, Enum):
    regression = "regression"
    classification = "classification"
    timeseries = "timeseries"
    clustering = "clustering"


class Semantic(str, Enum):
    numeric = "numeric"
    categorical = "categorical"
    datetime = "datetime"
    text = "text"
    boolean = "boolean"


# ---- Auth ----


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: datetime
    last_login_at: Optional[datetime] = None


class Token(BaseModel):
    """Token pair. ``refresh_token`` is also set as an HttpOnly cookie for browsers;
    it is echoed in the body for native/CLI clients that cannot use cookies."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0  # access-token lifetime, seconds
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional: browsers send the token in the HttpOnly cookie instead.
    refresh_token: Optional[str] = None


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class SsoProvider(BaseModel):
    name: str
    label: str


class AuthOptions(BaseModel):
    """What the login page needs to render itself."""

    password_login_enabled: bool = True
    providers: list[SsoProvider] = Field(default_factory=list)


# ---- Admin ----


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(viewer|user|admin)$")


class ActiveUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event: str
    actor_user_id: Optional[int] = None
    actor_email: Optional[str] = None
    target: Optional[str] = None
    outcome: str
    client_ip: Optional[str] = None
    request_id: Optional[str] = None
    detail_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SessionOut(BaseModel):
    """One live refresh token = one signed-in device."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    issued_at: datetime
    expires_at: datetime
    user_agent: Optional[str] = None
    client_ip: Optional[str] = None


# ---- Datasets ----


class ColumnSchema(BaseModel):
    name: str
    dtype: str
    semantic: str
    n_missing: int
    n_unique: int
    sample: list[Any]


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_format: str
    n_rows: int
    n_cols: int
    created_at: datetime


class DatasetDetail(DatasetOut):
    schema_json: dict[str, Any]


class PreviewOut(BaseModel):
    columns: list[ColumnSchema]
    rows: list[dict[str, Any]]
    n_rows: int
    n_cols: int


class TargetSuggestion(BaseModel):
    column: str
    reason: str


class DetectOut(BaseModel):
    suggested_task: TaskType
    candidate_targets: list[TargetSuggestion]
    datetime_columns: list[str]


# ---- Runs ----


class CleaningConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drop_duplicates: bool = True
    impute_numeric: str = Field(default="median", pattern="^(median|mean|zero|drop)$")
    impute_categorical: str = Field(default="mode", pattern="^(mode|constant|drop)$")
    drop_constant_columns: bool = True
    outlier_method: str = Field(default="none", pattern="^(none|iqr|zscore)$")


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: int = Field(gt=0)
    task_type: TaskType
    target_col: Optional[str] = Field(default=None, max_length=512)
    cleaning: CleaningConfig = CleaningConfig()

    @model_validator(mode="after")
    def _target_required_for_supervised(self) -> "RunCreate":
        supervised = (TaskType.regression, TaskType.classification, TaskType.timeseries)
        if self.task_type in supervised and not self.target_col:
            raise ValueError(f"target_col is required for {self.task_type.value} tasks")
        return self


class RunStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    stage: str
    progress: float
    message: Optional[str] = None
    best_model_id: Optional[int] = None


class RunOut(RunStatus):
    dataset_id: int
    task_type: str
    target_col: Optional[str] = None
    created_at: datetime


# ---- EDA ----


class ChartSpec(BaseModel):
    """A single Plotly-friendly chart payload."""

    id: str
    kind: str  # histogram|bar|heatmap|scatter|line|box
    title: str
    data: dict[str, Any]


class EdaOut(BaseModel):
    summary: dict[str, Any]
    charts: list[ChartSpec]
    report_url: Optional[str] = None


# ---- Leaderboard / models ----


class ModelResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_name: str
    family: str
    metrics_json: dict[str, Any]
    rank: int
    has_artifact: bool = False


class LeaderboardOut(BaseModel):
    primary_metric: Optional[str] = None
    best_model_id: Optional[int] = None
    models: list[ModelResultOut]


class ModelResultDetail(ModelResultOut):
    plots_json: dict[str, Any]


class PredictionOut(BaseModel):
    predictions: list[Any]
    n: int


# ---- Agentic AI layer ----


class AgentMode(str, Enum):
    advise = "advise"
    chat = "chat"
    copilot = "copilot"
    autopilot = "autopilot"


class AgentSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AgentMode
    run_id: Optional[int] = Field(default=None, gt=0)
    dataset_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _needs_a_subject(self) -> "AgentSessionCreate":
        if not self.run_id and not self.dataset_id:
            raise ValueError("provide run_id or dataset_id")
        return self


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    agent_name: Optional[str] = None
    content: Optional[str] = None
    tool_name: Optional[str] = None
    status: str
    created_at: datetime


class AgentSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mode: str
    status: str
    current_agent: Optional[str] = None
    run_id: Optional[int] = None
    dataset_id: Optional[int] = None
    created_at: datetime


class AgentProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: str
    proposed_config_json: dict[str, Any]
    status: str


class AgentSessionDetail(AgentSessionOut):
    error_json: dict[str, Any] = Field(default_factory=dict)
    messages: list[AgentMessageOut] = Field(default_factory=list)
    pending_proposal: Optional[AgentProposalOut] = None


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approve|reject)$")
    edited_config: Optional[dict[str, Any]] = None


class ChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


class AgentConfigItem(BaseModel):
    agent_name: str
    label: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True
    max_steps: Optional[int] = Field(default=None, ge=1, le=100)


class AgentConfigOut(BaseModel):
    provider: str
    enabled: bool
    available_models: dict[str, list[str]]
    provider_labels: dict[str, str] = Field(default_factory=dict)
    agents: list[AgentConfigItem]


class AgentConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentConfigItem]
