# API Reference

Base URL (dev): `http://localhost:8000`. Interactive docs at `/docs`.

All routes except `/api/health`, `/api/auth/register`, and `/api/auth/login` require a
bearer token:

```
Authorization: Bearer <access_token>
```

Datasets and runs are **scoped to the authenticated user** — you can only see your own.

---

## Auth

### `POST /api/auth/register`
Create an account and receive a token. Rate limited (default 10/min).

```json
// request
{ "email": "you@example.com", "password": "at-least-8-chars" }
// 201
{ "access_token": "eyJ...", "token_type": "bearer" }
```
`409` if the email is already registered.

### `POST /api/auth/login`
OAuth2 password flow — send **form-encoded** `username` (the email) and `password`.

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -d "username=you@example.com&password=at-least-8-chars"
```
`401` on bad credentials.

### `GET /api/auth/me`
Returns the current user `{ id, email, created_at }`.

---

## Datasets

### `POST /api/datasets`  *(multipart, rate limited 30/min)*
Upload a file (`file` field). Supported: `.csv .tsv .json .xlsx .xls .parquet`.
Returns the dataset with its inferred schema. Errors: `415` unsupported type,
`413` too large, `422` parse failure.

```bash
curl -H "Authorization: Bearer $TOK" -F "file=@data.csv" http://localhost:8000/api/datasets
```

### `GET /api/datasets`
List your datasets (newest first).

### `GET /api/datasets/{id}`
Dataset metadata + full column schema.

### `GET /api/datasets/{id}/preview`
Column schema + up to 50 sample rows.

### `POST /api/datasets/{id}/detect`
Suggest a problem type and candidate target columns:
```json
{ "suggested_task": "classification",
  "candidate_targets": [{ "column": "purchased", "reason": "..." }],
  "datetime_columns": [] }
```

### `DELETE /api/datasets/{id}`  → `204`

---

## Runs

### `POST /api/runs`  → `201`
Kick off a pipeline run. The run is **asynchronous** — it returns immediately with
`status: "queued"` and the full pipeline (clean → EDA → train → evaluate → persist)
executes in a background thread. The frontend polls `/status` for progress.

```json
{
  "dataset_id": 1,
  "task_type": "classification",         // regression|classification|timeseries|clustering
  "target_col": "purchased",             // required for supervised tasks
  "cleaning": {
    "drop_duplicates": true,
    "impute_numeric": "median",          // median|mean|zero|drop
    "impute_categorical": "mode",        // mode|constant|drop
    "drop_constant_columns": true,
    "outlier_method": "none"             // none|iqr|zscore
  }
}
```

Validation errors return `422`:
- Missing `target_col` for supervised task types.
- `target_col` not present in the dataset schema.
- Unknown fields rejected (`extra="forbid"`).

### `GET /api/runs`
List your runs (newest first).

### `GET /api/runs/{id}/status`
Poll the run's current state. Returns:

```json
{
  "id": 1,
  "status": "running",          // queued|running|done|error
  "stage": "training",          // queued|loading|cleaning|eda|training|finalizing|done|error
  "progress": 55.0,             // 0..100
  "message": "Training XGBoost",
  "best_model_id": null          // set once training completes
}
```

### `GET /api/runs/{id}/eda`
EDA payload:
```json
{
  "summary": { "n_rows": 5, "n_cols": 4, "n_numeric": 2, "total_missing": 1, "..." : "..." },
  "charts": [ { "id": "hist_age", "kind": "histogram", "title": "...", "data": {"..."} } ],
  "report_url": "/api/runs/1/report"
}
```
Chart `kind ∈ histogram|bar|heatmap|scatter|line|box`. The frontend renders these with Plotly.

`409` if the EDA stage has not completed yet.

### `GET /api/runs/{id}/report`
The self-contained HTML EDA report (`text/html`).

`404` if the report file was not generated or is missing.

---

## Leaderboard & Models *(Milestone 3)*

### `GET /api/runs/{id}/leaderboard`
Returns the ranked leaderboard for a completed training run.

```json
{
  "primary_metric": "f1_weighted",       // f1_weighted (classification) or rmse (regression)
  "best_model_id": 5,
  "models": [
    {
      "id": 5,
      "model_name": "XGBoost",
      "family": "boosting",
      "metrics_json": { "accuracy": 0.94, "f1_weighted": 0.93, "roc_auc": 0.98 },
      "rank": 1,
      "has_artifact": true
    },
    {
      "id": 3,
      "model_name": "Logistic Regression",
      "family": "linear",
      "metrics_json": { "accuracy": 0.88, "f1_weighted": 0.87, "roc_auc": 0.92 },
      "rank": 2,
      "has_artifact": false
    }
  ]
}
```

**Classification leaderboard** ranks by `f1_weighted` (higher is better).
**Regression leaderboard** ranks by `rmse` (lower is better).

Model families: `linear`, `tree`, `boosting`, `neighbors`, `bayes`.

### `GET /api/runs/{id}/models/{model_id}`
Full model detail, including evaluation plot payloads for rendering in the frontend.

```json
{
  "id": 5,
  "model_name": "XGBoost",
  "family": "boosting",
  "metrics_json": { "accuracy": 0.94, "f1_weighted": 0.93, "roc_auc": 0.98 },
  "rank": 1,
  "has_artifact": true,
  "plots_json": {
    "confusion_matrix": { "labels": ["0", "1"], "z": [[42, 3], [5, 50]] },
    "roc":              { "fpr": [0, 0.05, 1], "tpr": [0, 0.95, 1] },
    "feature_importance": { "features": ["age", "income"], "importance": [0.45, 0.32] }
  }
}
```

**Classification plots:** confusion matrix, ROC curve (binary), feature importance.
**Regression plots:** predicted-vs-actual scatter, residuals scatter, feature importance.

### `GET /api/runs/{id}/models/{model_id}/download`
Download the trained model artifact as a `.joblib` file.

```bash
curl -H "Authorization: Bearer $TOK" \
  http://localhost:8000/api/runs/1/models/5/download \
  -o best_model.joblib
```

Returns `application/octet-stream` with a `Content-Disposition` header.
Only the rank-1 (best) model has a persisted artifact. `404` if the artifact is not available.

---

## Predict *(Milestone 3)*

### `POST /api/runs/{id}/predict`
Upload new data rows and receive predictions from the run's best trained model.

```bash
curl -H "Authorization: Bearer $TOK" \
  -F "file=@new_rows.csv" \
  http://localhost:8000/api/runs/1/predict
```

The file can be any supported format (`.csv`, `.tsv`, `.json`, `.xlsx`, `.xls`, `.parquet`).
The model's bundled preprocessor transforms the input columns automatically — no manual
feature engineering needed.

**Response:**
```json
{
  "predictions": [1, 0, 1, 0, 1],
  "n": 5
}
```

| Error | Condition |
| ----- | --------- |
| `409` | No trained model available for this run. |
| `415` | Unsupported file format. |
| `422` | File parse failure or column mismatch. |

---

## Health

### `GET /api/health` → `{ "status": "ok", "app": "AutoDS" }`

## Error shape

Errors use FastAPI's convention:
```json
{ "detail": "human-readable message" }
```
Rate-limit breaches return `429 Too Many Requests`.
