# Getting Started

## Prerequisites

- Python 3.11+
- Node.js 20+ (22 recommended)
- (Optional) Docker, to run the full scalable stack

## 1. Start the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Verify: open http://localhost:8000/docs, or run the self-test:

```powershell
.\.venv\Scripts\python.exe smoke_test.py     # prints SMOKE_TEST_PASSED
```

## 2. Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## 3. Use it

1. **Register** an account (email + password, min 8 chars).
2. **Upload** a dataset â€” drag a CSV/JSON/Excel/Parquet file onto the dropzone.
3. On the dataset page, confirm the **problem type** and **target column** (pre-filled by
   auto-detection) and pick cleaning options.
4. Click **Run pipeline â†’ EDA**.
5. Explore the **EDA dashboard** â€” stat tiles, interactive charts, and a link to the full
   HTML report.

## 4. (Optional) Run the scalable stack

```bash
export PIPEFORGE_JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build --scale backend=3
# open http://localhost:8080
```

This brings up Postgres, Redis, three stateless backend replicas, and an nginx gateway
that load-balances across them. See [Deployment](../docs/DEPLOYMENT.md).

## Sample data to try

- **Classification** â€” any CSV with a low-cardinality last column (e.g. Iris, Titanic).
- **Regression** â€” a CSV with a continuous numeric target (e.g. housing prices).
- **Time series** â€” a CSV with a date column + a numeric value column.
