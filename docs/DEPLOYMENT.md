# Deployment

## Local development

Backend and frontend run as two dev servers; Vite proxies `/api` to the backend.

```powershell
# Backend
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend; npm install; npm run dev
```

Uses SQLite (`backend/storage/pipeforge.db`) and in-memory rate limiting â€” zero external
services required.

## Configuration (environment variables)

All settings are overridable with the `PIPEFORGE_` prefix (see `app/config.py`):

| Variable | Default | Notes |
| --- | --- | --- |
| `PIPEFORGE_DATABASE_URL` | SQLite file | Set to a `postgresql+psycopg://...` DSN for prod |
| `PIPEFORGE_JWT_SECRET` | dev placeholder | **Override** with a â‰¥32-byte random string |
| `PIPEFORGE_ACCESS_TOKEN_TTL_MINUTES` | 1440 | Token lifetime |
| `PIPEFORGE_RATELIMIT_STORAGE` | `memory://` | Set `redis://host:6379/0` for multi-replica |
| `PIPEFORGE_RATELIMIT_DEFAULT` / `_AUTH` / `_UPLOAD` | 200/10/30 per min | slowapi strings |
| `PIPEFORGE_CORS_ORIGINS` | localhost:5173 | JSON list of allowed origins |
| `PIPEFORGE_MAX_UPLOAD_BYTES` | 200 MB | Hard upload cap |
| `PIPEFORGE_STORAGE_SHARD_PREFIX_LEN` | 2 | Hex chars for the storage shard (2 â‡’ 256 shards) |

## Docker â€” horizontally scalable stack

The provided `docker-compose.yml` runs Postgres, Redis, N stateless backend replicas,
and an nginx gateway that serves the SPA and load-balances `/api`.

```bash
export PIPEFORGE_JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build --scale backend=3
# open http://localhost:8080
```

### How load balancing works

The nginx gateway (`frontend/nginx.frontend.conf`) proxies `/api` using a **variable**
upstream (`proxy_pass http://$backend_upstream:8000`) with Docker's embedded DNS resolver.
Docker resolves the `backend` service name to **all replica IPs** and nginx round-robins
across them at request time. Add or remove replicas and traffic rebalances automatically â€”
no config change.

### Why it scales

The backend keeps **no per-process state**:
- sessions â†’ **JWT** (any replica validates any token),
- metadata â†’ **Postgres**,
- rate-limit counters â†’ **Redis**,
- files â†’ the **shared `storage` volume**.

So `--scale backend=N` is safe for any N. In Kubernetes this maps to a `Deployment` with
`replicas: N` behind a `Service` + `Ingress`; use a `ReadWriteMany` PVC or object storage
(S3/GCS) for `storage`, a managed Postgres, and a managed Redis.

## Production checklist

1. **Secrets** â€” inject `PIPEFORGE_JWT_SECRET` and DB credentials via your secret manager.
2. **Database migrations** â€” replace startup `create_all` with an Alembic migration job
   so concurrent replicas don't race on DDL.
3. **TLS** â€” terminate at the gateway/ingress; add HSTS.
4. **Storage** â€” back the `storage` volume with durable object storage.
5. **Observability** â€” add structured logging, metrics (`/metrics`), and health/readiness
   probes (`/api/health`).
6. **Autoscaling** â€” scale the backend on CPU/latency; scale training workers separately
   once Milestone 3 lands.
