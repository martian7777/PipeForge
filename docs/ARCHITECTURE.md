# Architecture

AutoDS is a two-tier application — a React SPA and a FastAPI backend — designed to be
**stateless** on the backend so it scales horizontally.

```
┌──────────────────────────┐        HTTPS         ┌───────────────────────────────┐
│  React + Vite SPA         │  ───────────────▶    │  nginx gateway (load balancer) │
│  (auth, upload, EDA)      │  ◀───────────────    │  serves SPA, round-robins /api │
└──────────────────────────┘                       └───────────────┬───────────────┘
                                                                    │  /api
                                          ┌─────────────────────────┼─────────────────────────┐
                                          ▼                         ▼                          ▼
                                  ┌──────────────┐         ┌──────────────┐          ┌──────────────┐
                                  │ backend #1   │         │ backend #2   │   ...    │ backend #N   │
                                  │ FastAPI      │         │ FastAPI      │          │ FastAPI      │
                                  └──────┬───────┘         └──────┬───────┘          └──────┬───────┘
                                         └────────────────────────┼─────────────────────────┘
                                       shared state (no session affinity needed)
                          ┌───────────────────────┬───────────────────────┬─────────────────────┐
                          ▼                       ▼                       ▼
                   ┌────────────┐          ┌────────────┐          ┌──────────────────┐
                   │ PostgreSQL │          │   Redis    │          │ shared storage    │
                   │ (metadata) │          │ (limits)   │          │ (uploads/artifacts)│
                   └────────────┘          └────────────┘          └──────────────────┘
```

## Why the backend is stateless

- **Auth** is JWT bearer tokens — no server-side session store, so any replica can serve
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
| `api/runs.py`   | create run (clean + EDA), status, EDA payload, HTML report |
| `pipeline/*`    | `ingest`, `detect`, `clean`, `eda` (and `train`, `deep` in later milestones) |

## Data model

- **User** `1—N` **Dataset** `1—N` **Run** `1—N` **ModelResult**
- `Dataset.owner_id` scopes every dataset (and its runs/results) to a user; all queries
  filter by the authenticated user.
- `Run` stores the task type, target column, cleaning config, EDA payload (JSON), and a
  pointer to the generated HTML report. Model results (Milestone 3) attach here.

## The pipeline

Each stage is a pure-ish function `(DataFrame, config) -> (DataFrame/result, report)`,
so stages are independently testable:

1. **Ingest** (`ingest.py`) — multi-format load, encoding/delimiter sniffing, per-column
   semantic typing (numeric / categorical / datetime / text / boolean).
2. **Detect** (`detect.py`) — suggest task type + candidate targets (user-overridable).
3. **Clean** (`clean.py`) — datetime coercion, dedup, imputation, constant-column drop,
   optional outlier clipping; returns a report of exactly what changed.
4. **EDA** (`eda.py`) — summary stats + Plotly-friendly chart payloads (histograms, bar
   charts, correlation heatmap, target relationships, time-series line) + a self-contained
   HTML report.
5. **Train / Evaluate / Registry** — *Milestone 3+*; heavy work moves onto a
   `ProcessPoolExecutor` job runner with progress polling.

## Scaling notes / known limitations

- Table creation uses `create_all` on startup. For production with many replicas, switch
  to **Alembic migrations** run as a one-off job to avoid concurrent-DDL races.
- Milestone-2 runs execute cleaning + EDA **synchronously** in the request. Milestone 3
  introduces the async job runner for long training jobs (and a shared queue — e.g.
  Redis/RQ or Celery — when scaling training across workers).
