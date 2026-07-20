# AutoDS — End-to-End Data Science Pipeline Platform

Upload a data file, tell AutoDS what kind of problem it is (or let it guess), and it
runs the full standard data science pipeline for you: **ingest → clean/ETL → EDA →
AutoML training across model families → best-model selection → predict**.

| Layer     | Stack                                                                 |
| --------- | --------------------------------------------------------------------- |
| Frontend  | React 18 + Vite + TypeScript, Plotly charts (code-split)              |
| Backend   | FastAPI, SQLAlchemy 2, Pydantic v2                                     |
| Auth      | JWT bearer tokens (stateless), bcrypt password hashing                 |
| Storage   | Sharded local filesystem (dev) → shared volume / object store (prod)   |
| Database  | SQLite (dev) → PostgreSQL (prod / multi-replica)                       |
| Scaling   | Stateless replicas behind an nginx load balancer, Redis-backed limits  |
| ML (soon) | AutoML (FLAML/PyCaret), PyTorch (MLP + LSTM), classical time series    |

## Status

- ✅ **Milestone 1** — upload CSV/TSV/JSON/Excel/Parquet, schema inference, preview, task detection.
- ✅ **Milestone 2** — data cleaning/ETL, EDA (interactive charts + HTML report).
- ✅ **Platform hardening** — authentication, per-user data scoping, rate limiting,
  strict Pydantic validation, file-storage sharding, and a horizontally scalable
  deployment (nginx load balancer + backend replicas + Postgres + Redis).
- ⬜ **Milestone 3+** — AutoML model training, leaderboard, deep learning, predict + download.

See the full roadmap in [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation

| Doc | What's in it |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data model, pipeline stages |
| [docs/API.md](docs/API.md)                   | Full REST API reference with examples |
| [docs/SECURITY.md](docs/SECURITY.md)         | Auth, rate limiting, validation, hardening |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)     | Local, Docker, and horizontal-scaling deploy |
| [docs/ROADMAP.md](docs/ROADMAP.md)           | Milestone plan |
| [wiki/Home.md](wiki/Home.md)                 | Project wiki (getting started, FAQ, glossary) |

## Quick start (local dev)

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API docs (Swagger): http://localhost:8000/docs
- Self-test (no server needed): `.\.venv\Scripts\python.exe smoke_test.py`

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api to :8000)
```

Register an account in the UI, upload a dataset, pick the problem type + target, and
click **Run pipeline → EDA**.

## Run the full scalable stack (Docker)

```bash
# 3 backend replicas behind the nginx gateway, with Postgres + Redis:
docker compose up --build --scale backend=3
# open http://localhost:8080
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for details.

## Repository layout

```
ds/
├── backend/            FastAPI app
│   ├── app/
│   │   ├── api/        auth, datasets, runs routers
│   │   ├── pipeline/   ingest, detect, clean, eda (+ train/deep later)
│   │   ├── security.py JWT + bcrypt + current_user dependency
│   │   ├── storage.py  sharded file storage
│   │   ├── ratelimit.py slowapi limiter
│   │   ├── models.py   User, Dataset, Run, ModelResult
│   │   └── main.py     app factory, middleware, routers
│   ├── Dockerfile
│   └── requirements*.txt
├── frontend/           React + Vite SPA
│   ├── src/            auth, pages, components/Chart (Plotly)
│   ├── nginx.frontend.conf   gateway: static SPA + /api load balancing
│   └── Dockerfile
├── docs/               architecture, API, security, deployment, roadmap
├── wiki/               project wiki pages
└── docker-compose.yml  Postgres + Redis + scaled backend + nginx gateway
```
