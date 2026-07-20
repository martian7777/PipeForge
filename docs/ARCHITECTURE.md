# Architecture

PipeForge is a two-tier application â€” a React SPA and a FastAPI backend â€” designed to be
**stateless** on the backend so it scales horizontally.

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”        HTTPS         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  React + Vite SPA         â”‚  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¶    â”‚  nginx gateway (load balancer) â”‚
â”‚  (auth, upload, EDA)      â”‚  â—€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€    â”‚  serves SPA, round-robins /api â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                                                    â”‚  /api
                                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                                          â–¼                         â–¼                          â–¼
                                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                                  â”‚ backend #1   â”‚         â”‚ backend #2   â”‚   ...    â”‚ backend #N   â”‚
                                  â”‚ FastAPI      â”‚         â”‚ FastAPI      â”‚          â”‚ FastAPI      â”‚
                                  â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜         â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜          â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                       shared state (no session affinity needed)
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â–¼                       â–¼                       â–¼
                   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                   â”‚ PostgreSQL â”‚          â”‚   Redis    â”‚          â”‚ shared storage    â”‚
                   â”‚ (metadata) â”‚          â”‚ (limits)   â”‚          â”‚ (uploads/artifacts)â”‚
                   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Why the backend is stateless

- **Auth** is JWT bearer tokens â€” no server-side session store, so any replica can serve
  any request. See [SECURITY.md](SECURITY.md).
- **Metadata** (users, datasets, runs, results) lives in the database, not process memory.
- **Files** live on a shared volume / object store, addressed by a deterministic sharded
  key, so every replica resolves the same path.
- **Rate-limit counters** live in Redis in production, so a limit of "30 uploads/min"
  holds across the whole fleet rather than per process.

This means scaling is just "run more backend containers"; no sticky sessions.

## Backend modules (`backend/app`)

| Module          | Responsibility |
| --------------- | -------------- |
| `config.py`     | Settings (env-overridable): DB URL, JWT, rate limits, storage, sharding |
| `db.py`         | SQLAlchemy engine/session, `init_db()` (create tables + storage dirs) |
| `models.py`     | ORM: `User`, `Dataset`, `Run`, `ModelResult` |
| `schemas.py`    | Pydantic request/response models (strict, enum-typed, validated) |
| `security.py`   | Password hashing, JWT issue/verify, `current_user` dependency |
| `ratelimit.py`  | slowapi limiter (memory or Redis backend) |
| `storage.py`    | Sharded upload/artifact path resolution |
| `api/auth.py`   | `register`, `login`, `me` |
| `api/datasets.py` | upload, list, detail, preview, detect, delete (per-user scoped) |
| `api/runs.py`   | create run (async), status, EDA, leaderboard, model detail/download, predict |
| `jobs/runner.py` | `ThreadPoolExecutor` background runner; writes stage + progress to DB |
| `pipeline/ingest.py` | Multi-format loader, encoding/delimiter sniffing, semantic typing |
| `pipeline/detect.py` | Task type + target column suggestion |
| `pipeline/clean.py`  | Datetime coercion, dedup, imputation, outlier handling |
| `pipeline/eda.py`    | Summary stats, Plotly chart payloads, HTML report generation |
| `pipeline/features.py` | `ColumnTransformer` preprocessor (numeric/categorical/datetime) |
| `pipeline/model_zoo.py` | Classification & regression candidate model definitions |
| `pipeline/train.py`  | Model sweep, holdout split, fit/score/rank, feature importance extraction |
| `pipeline/evaluate.py` | Task-specific metrics (F1/accuracy/AUC, RMSE/MAE/RÂ²) + eval-plot payloads |
| `pipeline/registry.py` | Best model persistence (joblib) and inference at prediction time |

## Data model

- **User** `1â€”N` **Dataset** `1â€”N` **Run** `1â€”N` **ModelResult**
- `Dataset.owner_id` scopes every dataset (and its runs/results) to a user; all queries
  filter by the authenticated user.
- `Run` stores the task type, target column, cleaning config, EDA payload (JSON), a
  pointer to the generated HTML report, and `best_model_id` (the rank-1 model).
- `ModelResult` stores each trained candidate: name, family, metrics (JSON), eval-plot
  payloads (JSON), artifact path (joblib), and rank.

## The pipeline

Each stage is a pure-ish function `(DataFrame, config) -> (DataFrame/result, report)`,
so stages are independently testable:

1. **Ingest** (`ingest.py`) â€” multi-format load, encoding/delimiter sniffing, per-column
   semantic typing (numeric / categorical / datetime / text / boolean).
2. **Detect** (`detect.py`) â€” suggest task type + candidate targets (user-overridable).
3. **Clean** (`clean.py`) â€” datetime coercion, dedup, imputation, constant-column drop,
   optional outlier clipping; returns a report of exactly what changed.
4. **EDA** (`eda.py`) â€” summary stats + Plotly-friendly chart payloads (histograms, bar
   charts, correlation heatmap, target relationships, time-series line) + a self-contained
   HTML report.
5. **Features** (`features.py`) â€” infer feature spec (numeric/categorical/datetime),
   build a `ColumnTransformer` preprocessor bundled into each sklearn `Pipeline`.
6. **Train** (`train.py`) â€” sweep the model zoo, holdout split (80/20, stratified for
   classification), fit each candidate, collect metrics + eval-plot payloads, rank by
   the primary metric, extract feature importances.
7. **Evaluate** (`evaluate.py`) â€” classification metrics (accuracy, F1, ROC AUC) and
   regression metrics (RMSE, MAE, RÂ²). Chart payloads: confusion matrix, ROC curve,
   predicted-vs-actual, residuals, feature importance.
8. **Registry** (`registry.py`) â€” persist the best model artifact (joblib with metadata)
   and load it for predictions on new data at inference time.

Stages 1â€“4 run for all task types. Stages 5â€“8 run for supervised tabular tasks
(classification, regression). The `jobs/runner.py` orchestrates the full sequence in a
background thread, reporting `stage` + `progress` to the DB for frontend polling.

## Scaling notes / known limitations

- Table creation uses `create_all` on startup. For production with many replicas, switch
  to **Alembic migrations** run as a one-off job to avoid concurrent-DDL races.
- Pipeline runs are **asynchronous** via a `ThreadPoolExecutor` in-process job runner.
  For production at scale, swap for a shared queue (Redis/RQ or Celery) so training
  workers scale independently of the API replicas.
- Only the rank-1 (best) model artifact is persisted to disk; other candidates' weights
  are discarded after scoring.
