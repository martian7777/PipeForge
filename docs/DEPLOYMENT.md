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
| `PIPEFORGE_ACCESS_TOKEN_TTL_MINUTES` | 15 | Access-token lifetime (short by design) |
| `PIPEFORGE_REFRESH_TOKEN_TTL_DAYS` | 14 | Refresh-token lifetime |
| `PIPEFORGE_REFRESH_COOKIE_SECURE` | `false` | Set `true` behind TLS; also enables HSTS |
| `PIPEFORGE_BOOTSTRAP_ADMIN_EMAIL` | _(blank)_ | Promoted to admin; blank â‡’ first registrant |
| `PIPEFORGE_AUTO_CREATE_TABLES` | `true` | Set `false` in prod and run Alembic |
| `PIPEFORGE_RATELIMIT_STORAGE` | `memory://` | Set `redis://host:6379/0` for multi-replica |
| `PIPEFORGE_RATELIMIT_DEFAULT` / `_AUTH` / `_UPLOAD` / `_AGENT` | 200/10/30/60 per min | slowapi strings |
| `PIPEFORGE_CORS_ORIGINS` | localhost:5173 | JSON list of allowed origins |
| `PIPEFORGE_MAX_UPLOAD_BYTES` | 200 MB | Hard upload cap |
| `PIPEFORGE_STORAGE_SHARD_PREFIX_LEN` | 2 | Hex chars for the storage shard (2 â‡’ 256 shards) |
| `PIPEFORGE_LOG_FORMAT` | `json` | `console` for readable local output |
| `PIPEFORGE_LOG_LEVEL` | `INFO` | Root log level |
| `PIPEFORGE_AUDIT_TO_DB` | `true` | Also persist audit events to `audit_log` |

### Single sign-on (OAuth 2.0 / OIDC)

A provider activates as soon as its client id and secret are present. See
[SECURITY.md](SECURITY.md#single-sign-on-oauth-20--oidc) for how the flow is secured.

| Variable | Notes |
| --- | --- |
| `PIPEFORGE_PUBLIC_BASE_URL` | Public origin as the browser sees it. **Redirect URIs derive from this.** |
| `PIPEFORGE_GOOGLE_CLIENT_ID` / `_SECRET` | Google Cloud console â†’ OAuth 2.0 Client ID |
| `PIPEFORGE_GITHUB_CLIENT_ID` / `_SECRET` | GitHub â†’ Settings â†’ Developer settings â†’ OAuth Apps |
| `PIPEFORGE_MICROSOFT_CLIENT_ID` / `_SECRET` | Entra ID â†’ App registrations |
| `PIPEFORGE_MICROSOFT_TENANT` | `common` (default), `organizations`, or a tenant GUID |
| `PIPEFORGE_OAUTH_ALLOWED_EMAIL_DOMAINS` | JSON list, e.g. `["yourcompany.com"]`. Empty â‡’ any |

Register this redirect URI with each provider, exactly:

```
{PIPEFORGE_PUBLIC_BASE_URL}/api/auth/oauth/{google|microsoft|github}/callback
```

For local development that is `http://localhost:5173/api/auth/oauth/google/callback`
(Vite proxies `/api` to the backend); in the Docker stack it is port `8080`.

## Database migrations

Schema is managed with **Alembic**. `create_all` remains only as a local convenience — it
creates missing tables but never alters existing ones, so it cannot apply changes.

```bash
cd backend
alembic upgrade head            # apply everything
alembic current                 # show current revision
alembic downgrade -1            # roll back one
alembic revision --autogenerate -m "describe change"
```

**Upgrading a database that predates migrations** (one built by `create_all`) — mark it as
already holding the initial schema, then apply the rest:

```bash
alembic stamp 0001
alembic upgrade head
```

The `0002` migration promotes the first existing user to `admin`, so an upgraded
deployment is never left without one.

In Docker this is automatic: `docker-entrypoint.sh` runs `alembic upgrade head` before
uvicorn starts. Alembic locks the version table, so concurrent replicas serialize — the
first applies the migrations and the rest see the database is already at head. That makes
`--scale backend=N` safe without a separate migration job.

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

### Health probes

| Endpoint | Meaning | Use for |
| --- | --- | --- |
| `GET /api/health` | Liveness â€” process is up. Does **not** touch the database. | Restart policy |
| `GET /api/health/ready` | Readiness â€” database reachable. Returns **503** when not. | Load-balancer pool membership |

Point the balancer at `/api/health/ready` so a replica with a broken database connection
drains instead of receiving traffic it cannot serve.

## Production checklist

1. **Secrets** â€” inject `PIPEFORGE_JWT_SECRET` and DB credentials via your secret manager.
2. **Database migrations** â€” set `PIPEFORGE_AUTO_CREATE_TABLES=false`; the entrypoint runs
   `alembic upgrade head`, and Alembic's version-table lock keeps concurrent replicas from
   racing on DDL.
3. **TLS** â€” terminate at the gateway/ingress; set `PIPEFORGE_REFRESH_COOKIE_SECURE=true`,
   which marks the refresh cookie `Secure` and enables HSTS.
4. **SSO** â€” set `PIPEFORGE_PUBLIC_BASE_URL` to the real public origin before registering
   redirect URIs, and consider `PIPEFORGE_OAUTH_ALLOWED_EMAIL_DOMAINS` for internal
   deployments.
5. **Storage** — back the `storage` volume with durable object storage.
6. **Observability** — logs are already structured JSON on stdout with a request id per
   line; ship them to a searchable store and alert on `auth.refresh.reuse_detected`,
   `authz.denied`, `startup.insecure_config`, and `http.unhandled_exception`. Wire the
   probes above; metrics (`/metrics`) are still outstanding.
7. **Autoscaling** — scale the backend on CPU/latency; scale training workers separately.
8. **First admin** — set `PIPEFORGE_BOOTSTRAP_ADMIN_EMAIL` so admin isn't granted by
   whoever registers first.

## CI/CD Pipeline

PipeForge uses GitHub Actions for Continuous Integration and Continuous Delivery:

- **Continuous Integration (`.github/workflows/ci.yml`):**
  - **Backend Pipeline:** Runs Ruff syntax checking, installs dependencies, and executes end-to-end Python smoke tests (`smoke_test.py` and `smoke_train.py`).
  - **Frontend Pipeline:** Runs TypeScript type checks (`tsc -b`) and validates production Vite builds (`npm run build`).
  - **Docker Pipeline:** Validates `docker-compose.yml` topology and builds test container images for backend and frontend.

- **Continuous Delivery (`.github/workflows/cd.yml`):**
  - Triggered automatically on version tags (e.g. `v1.0.0`).
  - Builds optimized multi-stage Docker containers and publishes them to **GitHub Container Registry (GHCR)**:
    - `ghcr.io/<owner>/pipeforge/backend:latest`
    - `ghcr.io/<owner>/pipeforge/frontend:latest`
