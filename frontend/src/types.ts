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

export interface AuthUser {
  id: number;
  email: string;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
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
