# Security

## Authentication & authorization

- **JWT bearer tokens** (HS256), issued on register/login, verified on every protected
  request via the `current_user` dependency (`app/security.py`). Tokens are stateless —
  no server-side session — so the fleet scales without sticky sessions.
- **Passwords** are hashed with **bcrypt** (per-password salt). Plaintext is never stored.
- **Per-user data isolation**: every dataset/run query filters by `owner_id`. Requesting
  another user's dataset returns `404` (not `403`, to avoid confirming existence).
- Configure via env: `AUTODS_JWT_SECRET` (**must** be a ≥32-byte random string in prod),
  `AUTODS_ACCESS_TOKEN_TTL_MINUTES`.

Generate a secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Input validation

- All request bodies are **Pydantic v2** models with `extra="forbid"` — unknown fields
  are rejected, not silently ignored.
- Enums (`TaskType`) and field constraints (`min_length`, regex patterns for cleaning
  strategies) reject malformed input at the boundary.
- A model-level validator enforces cross-field rules (e.g. supervised tasks require a
  `target_col`).
- Uploads are validated by extension and **streamed with a hard size cap**
  (`AUTODS_MAX_UPLOAD_BYTES`, default 200 MB) to prevent memory exhaustion; parse
  failures are caught and the partial file removed.

## Rate limiting

- **slowapi** limits by client IP (`app/ratelimit.py`). Defaults: 200/min global,
  10/min on auth endpoints, 30/min on uploads. Breaches return `429`.
- Storage backend is configurable: in-memory for a single process, or **Redis**
  (`AUTODS_RATELIMIT_STORAGE=redis://...`) so limits are enforced **across all replicas**.
- Behind the nginx gateway, uvicorn runs with `--proxy-headers` so the real client IP
  (from `X-Forwarded-For`) is used, not the proxy's.

## Transport & headers

- A middleware sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and
  `Referrer-Policy: no-referrer` on every response.
- **CORS** is restricted to configured origins (`AUTODS_CORS_ORIGINS`). In the Docker
  topology the SPA and API are same-origin through nginx, so CORS is effectively closed.
- Terminate **TLS** at the gateway / ingress in production (not shown in the sample
  compose file).

## File storage

- Uploaded files are stored under a **sharded, non-guessable key** (`uuid4` + extension)
  rather than the user-supplied filename, avoiding path traversal and hot directories.

## Hardening checklist for production

- [ ] Set a strong `AUTODS_JWT_SECRET` and rotate periodically.
- [ ] Use Postgres + Redis (not SQLite / in-memory limits).
- [ ] Terminate TLS and set HSTS at the ingress.
- [ ] Run DB schema via **Alembic migrations**, not `create_all`, at scale.
- [ ] Add refresh-token rotation / token revocation if long sessions are needed.
- [ ] Put the storage volume on durable, backed-up object storage.
- [ ] Scan images and pin dependency versions.
