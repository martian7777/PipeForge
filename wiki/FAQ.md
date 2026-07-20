# FAQ & Troubleshooting

### What file formats can I upload?
CSV, TSV, JSON (records, columnar, or line-delimited), Excel (`.xlsx`/`.xls`), and
Parquet. Encoding and delimiter are auto-sniffed for delimited files.

### Does it train models yet?
Not yet â€” Milestones 1â€“2 (ingest, clean, EDA) are complete. Model training, the
leaderboard, deep learning, and prediction land in Milestone 3+. See the
[Roadmap](../docs/ROADMAP.md).

### Why do I have to log in?
Data is isolated per user. Auth is JWT-based so the backend stays stateless and scalable.
Register in the UI or via `POST /api/auth/register`.

### I get `401 Unauthorized`.
Your token is missing or expired. Sign in again (tokens last 24h by default,
configurable via `PIPEFORGE_ACCESS_TOKEN_TTL_MINUTES`).

### I get `429 Too Many Requests`.
You hit a rate limit (defaults: 200/min general, 10/min auth, 30/min upload). Wait and
retry, or raise the limits via `PIPEFORGE_RATELIMIT_*` env vars.

### My upload fails with `413`.
The file exceeds the 200 MB cap (`PIPEFORGE_MAX_UPLOAD_BYTES`). Raise it or split the file.

### VS Code shows thousands of pending git changes.
That's a stale view from before `.gitignore` existed. `.venv/`, `node_modules/`, and
build artifacts are all ignored â€” `git status` shows only real source files. Reload the
window or run `git status` to confirm.

### How do I switch from SQLite to Postgres?
Set `PIPEFORGE_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db`. The Docker compose
stack does this automatically. Install `psycopg` (in `requirements-prod.txt`).

### How does horizontal scaling work?
Run more backend replicas (`docker compose up --scale backend=3`). The nginx gateway
round-robins across them via Docker DNS. The backend is stateless (JWT + Postgres + Redis
+ shared storage), so any replica handles any request. See
[Deployment](../docs/DEPLOYMENT.md).

### Where are uploaded files and the database stored?
Locally under `backend/storage/` (gitignored). In Docker, on named volumes (`storage`,
`pgdata`). Files use sharded, non-guessable keys.

### The EDA report link 404s.
The HTML report is generated per run and served at `/api/runs/{id}/report`. If a run
errored, no report exists â€” check `GET /api/runs/{id}/status` for the error message.
