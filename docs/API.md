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

## Runs (clean + EDA)

### `POST /api/runs`  → `201`
Kick off a pipeline run (Milestone 2: cleaning + EDA, synchronous).

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
Validation errors return `422` (e.g. missing `target_col` for a supervised task, or a
`target_col` not present in the dataset). Unknown fields are rejected.

### `GET /api/runs`
List your runs.

### `GET /api/runs/{id}/status`
`{ id, status, stage, progress, message, best_model_id }` —
`status ∈ queued|running|done|error`.

### `GET /api/runs/{id}/eda`
EDA payload:
```json
{
  "summary": { "n_rows": 5, "n_cols": 4, "n_numeric": 2, "total_missing": 1, ... },
  "charts": [ { "id": "hist_age", "kind": "histogram", "title": "...", "data": {...} } ],
  "report_url": "/api/runs/1/report"
}
```
Chart `kind ∈ histogram|bar|heatmap|scatter|line`. The frontend renders these with Plotly.

### `GET /api/runs/{id}/report`
The self-contained HTML EDA report (`text/html`).

---

## Health

### `GET /api/health` → `{ "status": "ok", "app": "AutoDS" }`

## Error shape

Errors use FastAPI's convention:
```json
{ "detail": "human-readable message" }
```
Rate-limit breaches return `429 Too Many Requests`.
