# API Reference

Base URL (dev): `http://localhost:8000`. Interactive docs at `/api/docs`.

All routes except `/api/health*`, `/api/auth/options`, `/api/auth/register`,
`/api/auth/login`, `/api/auth/refresh`, and the `/api/auth/oauth/*` flow require a bearer
token:

```
Authorization: Bearer <access_token>
```

Datasets and runs are **scoped to the authenticated user** â€” you can only see your own.

### Error format

Every error returns the same envelope. `detail` is kept for convenience; `error` carries
the machine-readable type and the `request_id` to quote when reporting a problem (it is
also echoed as the `X-Request-ID` response header).

```json
{
  "detail": "Request validation failed",
  "error": {
    "type": "validation_error",
    "message": "Request validation failed",
    "request_id": "3f2c9a1b...",
    "details": [{ "field": "password", "message": "String should have at least 12 characters", "type": "string_too_short" }]
  }
}
```

Types: `bad_request` `unauthenticated` `forbidden` `not_found` `conflict`
`payload_too_large` `unsupported_media_type` `validation_error` `rate_limited`
`internal_error` `service_unavailable`.

---

## Auth

Tokens come in pairs. The **access token** (15 min) goes in the `Authorization` header.
The **refresh token** (14 days) is also set as an HttpOnly cookie scoped to `/api/auth`,
and echoed in the body for non-browser clients. See
[SECURITY.md](SECURITY.md#tokens) for the rotation and revocation model.

### `GET /api/auth/options`  *(public)*
What sign-in methods this deployment offers â€” used to render the login page.

```json
{ "password_login_enabled": true, "providers": [{ "name": "google", "label": "Google" }] }
```

### `POST /api/auth/register`
Create an account and receive a token pair. Rate limited (default 10/min).

```json
// request
{ "email": "you@example.com", "password": "at-least-12-chars", "full_name": null }
// 201
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 900, "refresh_token": "eyJ..." }
```
`409` if the email is already registered. The first account registered (or the one named
by `PIPEFORGE_BOOTSTRAP_ADMIN_EMAIL`) becomes `admin`.

### `POST /api/auth/login`
OAuth 2.0 password grant â€” send **form-encoded** `username` (the email) and `password`.

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -d "username=you@example.com&password=at-least-12-chars"
```
`401` on bad credentials (identical message for unknown user and wrong password).
`403` if the account is disabled.

### `POST /api/auth/refresh`
Rotate a refresh token into a new pair. Reads the HttpOnly cookie, or takes
`{"refresh_token": "..."}` in the body.

`401` if the token is unknown, expired, revoked, or **already used** â€” reuse revokes the
entire token family.

### `POST /api/auth/logout`  → `204`
Revoke the presented refresh token and clear the cookie. Idempotent.

### `POST /api/auth/logout-all`  → `204`
Revoke every session for the caller and invalidate all outstanding access tokens.

### `POST /api/auth/password`  → `204`
`{ "current_password": "...", "new_password": "..." }`. Signs the user out everywhere.
`400` if the current password is wrong.

### `GET /api/auth/me`
Returns `{ id, email, full_name, avatar_url, role, is_active, created_at, last_login_at }`.

### `GET /api/auth/sessions`
The caller's live sign-ins: `[{ id, issued_at, expires_at, user_agent, client_ip }]`.

### Single sign-on

### `GET /api/auth/oauth/{provider}/authorize?next=/`
Browser redirect that starts the authorization-code + PKCE flow. `provider` is
`google`, `github`, or `microsoft`. `404` if that provider is not configured.
Navigate to it â€” do not fetch it.

### `GET /api/auth/oauth/{provider}/callback`
The provider's redirect target. On success it sets the refresh cookie and redirects to
the SPA at `/auth/callback` â€” **no tokens appear in the URL**. On failure it redirects to
`/login?sso_error=...`.

---

## Admin  *(requires the `admin` role)*

All routes return `403` for non-admins.

### `GET /api/admin/users?q=&limit=&offset=`
List users, newest first. `q` filters by email substring.

### `PATCH /api/admin/users/{id}/role`
`{ "role": "viewer" | "user" | "admin" }`. Invalidates that user's outstanding access
tokens. `400` if demoting yourself or the last active admin.

### `PATCH /api/admin/users/{id}/active`
`{ "is_active": false }`. Disabling also revokes every session immediately.
`400` if disabling yourself or the last active admin.

### `POST /api/admin/users/{id}/revoke-sessions`  → `204`
Force a user off every device.

### `GET /api/admin/audit?event_prefix=&actor_user_id=&outcome=&limit=&offset=`
The audit trail, newest first. Filter by dotted event prefix (`auth.`, `admin.`,
`dataset.`), actor, or `success`/`failure`.

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

### `DELETE /api/datasets/{id}`  â†’ `204`

---

## Runs

### `POST /api/runs`  â†’ `201`
Kick off a pipeline run. The run is **asynchronous** â€” it returns immediately with
`status: "queued"` and the full pipeline (clean â†’ EDA â†’ train â†’ evaluate â†’ persist)
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
Chart `kind âˆˆ histogram|bar|heatmap|scatter|line|box`. The frontend renders these with Plotly.

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
The model's bundled preprocessor transforms the input columns automatically â€” no manual
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

### `GET /api/health` â†’ `{ "status": "ok", "app": "PipeForge" }`

## Error shape

Errors use FastAPI's convention:
```json
{ "detail": "human-readable message" }
```
Rate-limit breaches return `429 Too Many Requests`.
