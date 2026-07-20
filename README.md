# PipeForge — End-to-End Data Science Pipeline Platform

Upload a data file, tell PipeForge what kind of problem it is (or let it guess), and it
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
| ML        | Sklearn pipelines, XGBoost, LightGBM, classical estimators (model zoo)|

## Status

- ✅ **Milestone 1** — upload CSV/TSV/JSON/Excel/Parquet, schema inference, preview, task detection.
- ✅ **Milestone 2** — data cleaning/ETL, EDA (interactive charts + HTML report).
- ✅ **Platform hardening** — authentication, per-user data scoping, rate limiting,
  strict Pydantic validation, file-storage sharding, and a horizontally scalable
  deployment (nginx load balancer + backend replicas + Postgres + Redis).
- ✅ **Milestone 3** — AutoML: async job runner, a model zoo (linear/tree/**XGBoost/
  LightGBM**/KNN/NB) trained + ranked into a **leaderboard**, eval charts (confusion/ROC/
  residuals/feature-importance), best-model **download**, and **predict** on new data.
- ⬜ **Milestone 4+** — deep learning (PyTorch MLP + LSTM), time series, tuning + SHAP.

See the full roadmap in [docs/ROADMAP.md](docs/ROADMAP.md).

## AutoML — what you get (Milestone 3)

PipeForge trains **8 candidate models** per run and ranks them into a leaderboard:

| Family    | Classification models                  | Regression models                    |
| --------- | -------------------------------------- | ------------------------------------ |
| Linear    | Logistic Regression                    | Linear Regression, Ridge             |
| Tree      | Random Forest, Extra Trees             | Random Forest, Extra Trees           |
| Boosting  | Gradient Boosting, XGBoost, LightGBM   | Gradient Boosting, XGBoost, LightGBM |
| Neighbors | K-Nearest Neighbors                    | K-Nearest Neighbors                  |
| Bayes     | Gaussian Naive Bayes                   | —                                    |

Each candidate is trained inside a `Pipeline(preprocessor, model)` — numeric columns are
imputed + scaled, categoricals are imputed + one-hot encoded (up to 50 categories),
datetimes are expanded into year/month/day/day-of-week features. The full pipeline is
persisted as a single `.joblib` artifact so predictions on new data require no manual
feature engineering.

**Evaluation:** classification → accuracy, weighted F1, ROC AUC · regression → RMSE, MAE, R².
**Eval charts:** confusion matrix, ROC curve, predicted-vs-actual, residuals, feature importance.

## Documentation

| Doc | What's in it |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data model, pipeline stages |
| [docs/API.md](docs/API.md)                   | Full REST API reference with examples |
| [docs/SECURITY.md](docs/SECURITY.md)         | Auth, rate limiting, validation, hardening |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)     | Local, Docker, and horizontal-scaling deploy |
| [docs/ROADMAP.md](docs/ROADMAP.md)           | Milestone plan and detailed changelog |
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
click **Run pipeline**. The pipeline runs asynchronously — watch the progress bar as it
cleans, generates EDA charts, trains models, and builds the leaderboard. When it
finishes, explore the eval charts, download the best model, or predict on new data.

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
│   │   │               (leaderboard, model detail/download, predict)
│   │   ├── pipeline/   ingest, detect, clean, eda, features, model_zoo,
│   │   │               train, evaluate, registry
│   │   ├── jobs/       async job runner (ThreadPoolExecutor, DB progress)
│   │   ├── security.py JWT + bcrypt + current_user dependency
│   │   ├── storage.py  sharded file storage
│   │   ├── ratelimit.py slowapi limiter
│   │   ├── models.py   User, Dataset, Run, ModelResult
│   │   ├── schemas.py  Pydantic v2 request/response models (strict)
│   │   └── main.py     app factory, middleware, routers
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/           React + Vite SPA
│   ├── src/            auth, pages, components/Chart (Plotly)
│   │                   progress polling, leaderboard, eval charts,
│   │                   model download, predict widget
│   ├── nginx.frontend.conf   gateway: static SPA + /api load balancing
│   └── Dockerfile
├── docs/               architecture, API, security, deployment, roadmap
├── wiki/               project wiki pages
└── docker-compose.yml  Postgres + Redis + scaled backend + nginx gateway
```
