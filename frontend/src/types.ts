// Shared types mirroring the backend Pydantic schemas.

export interface ColumnSchema {
  name: string;
  dtype: string;
  semantic: "numeric" | "categorical" | "datetime" | "text" | "boolean";
  n_missing: number;
  n_unique: number;
  sample: unknown[];
}

export interface Dataset {
  id: number;
  filename: string;
  file_format: string;
  n_rows: number;
  n_cols: number;
  created_at: string;
}

export interface DatasetDetail extends Dataset {
  schema_json: { columns: ColumnSchema[] };
}

export interface Preview {
  columns: ColumnSchema[];
  rows: Record<string, unknown>[];
  n_rows: number;
  n_cols: number;
}

export interface TargetSuggestion {
  column: string;
  reason: string;
}

export interface DetectResult {
  suggested_task: string;
  candidate_targets: TargetSuggestion[];
  datetime_columns: string[];
}

export type Role = "viewer" | "user" | "admin";

export interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string | null;
}

export interface SsoProvider {
  name: string;
  label: string;
}

export interface AuthOptions {
  password_login_enabled: boolean;
  providers: SsoProvider[];
}

export interface SessionInfo {
  id: number;
  issued_at: string;
  expires_at: string;
  user_agent: string | null;
  client_ip: string | null;
}

export interface AuditEntry {
  id: number;
  event: string;
  actor_user_id: number | null;
  actor_email: string | null;
  target: string | null;
  outcome: "success" | "failure";
  client_ip: string | null;
  request_id: string | null;
  detail_json: Record<string, unknown>;
  created_at: string;
}

/** The structured error envelope every API failure returns. */
export interface ApiErrorBody {
  detail: string;
  error: {
    type: string;
    message: string;
    request_id: string | null;
    details?: unknown;
  };
}

export interface CleaningConfig {
  drop_duplicates: boolean;
  impute_numeric: "median" | "mean" | "zero" | "drop";
  impute_categorical: "mode" | "constant" | "drop";
  drop_constant_columns: boolean;
  outlier_method: "none" | "iqr" | "zscore";
}

export interface RunOut {
  id: number;
  status: string;
  stage: string;
  progress: number;
  message: string | null;
  best_model_id: number | null;
  dataset_id: number;
  task_type: string;
  target_col: string | null;
  created_at: string;
}

export interface ChartSpec {
  id: string;
  kind: "histogram" | "bar" | "heatmap" | "scatter" | "line" | "box";
  title: string;
  data: Record<string, unknown>;
}

export interface EdaResult {
  summary: Record<string, unknown>;
  charts: ChartSpec[];
  report_url: string | null;
}

export interface RunStatus {
  id: number;
  status: "queued" | "running" | "done" | "error";
  stage: string;
  progress: number;
  message: string | null;
  best_model_id: number | null;
}

export interface ModelResult {
  id: number;
  model_name: string;
  family: string;
  metrics_json: Record<string, number>;
  rank: number;
  has_artifact: boolean;
}

export interface Leaderboard {
  primary_metric: string | null;
  best_model_id: number | null;
  models: ModelResult[];
}

export interface ModelDetail extends ModelResult {
  plots_json: Record<string, unknown>;
}

export interface Prediction {
  predictions: unknown[];
  n: number;
}

// --- Agentic AI layer ---

export type AgentMode = "advise" | "chat" | "copilot" | "autopilot";

export interface AgentMessage {
  id: number;
  role: "system" | "user" | "assistant" | "tool" | "error";
  agent_name: string | null;
  content: string | null;
  tool_name: string | null;
  status: "running" | "done" | "error";
  created_at: string;
}

export interface AgentSession {
  id: number;
  mode: string;
  status: "running" | "awaiting_approval" | "done" | "error";
  current_agent: string | null;
  run_id: number | null;
  dataset_id: number | null;
  created_at: string;
}

export interface AgentProposal {
  id: number;
  stage: string;
  proposed_config_json: Record<string, unknown>;
  status: string;
}

export interface AgentSessionDetail extends AgentSession {
  error_json: Record<string, unknown>;
  messages: AgentMessage[];
  pending_proposal: AgentProposal | null;
}

export interface AgentConfigItem {
  agent_name: string;
  label: string | null;
  provider: string | null;
  model: string | null;
  enabled: boolean;
  max_steps: number | null;
}

export interface AgentConfig {
  provider: string;
  enabled: boolean;
  available_models: Record<string, string[]>;
  provider_labels: Record<string, string>;
  agents: AgentConfigItem[];
}
