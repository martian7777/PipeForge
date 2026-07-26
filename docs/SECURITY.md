# Security

## Authentication

Three ways in, all ending at the same session issuer.

### Password

`POST /api/auth/register` and `POST /api/auth/login` (OAuth 2.0 password-grant form
encoding). Passwords are hashed with **bcrypt** (per-password salt); plaintext is never
stored, and a minimum length of 12 is enforced at the schema boundary.

Login returns an identical `401 Incorrect email or password` whether the account exists
or the password was wrong, so the endpoint cannot be used to enumerate registered
addresses.

### Single sign-on (OAuth 2.0 / OIDC)

`GET /api/auth/oauth/{provider}/authorize` → provider → `GET /api/auth/oauth/{provider}/callback`.

Providers: **Google**, **Microsoft Entra ID**, **GitHub**. Each turns on simply by
supplying a client id and secret; the login page renders buttons for whatever is
configured (`GET /api/auth/options`).

The flow is **authorization code with PKCE** (RFC 7636), and every defence in it is
load-bearing:

| Mechanism | What it stops |
| --- | --- |
| **PKCE** (`S256`) | A stolen authorization code cannot be redeemed without the per-request `code_verifier`, which never leaves our origin. |
| **`state`** | CSRF on the callback — a forged redirect carries a state that does not match the browser's cookie. |
| **`nonce`** | Replay of an `id_token` minted for a different session. |
| **`id_token` verification** | Signature checked against the provider's **live JWKS**, plus audience, issuer and expiry. Identity comes from the verified token, not an unauthenticated userinfo response. |
| **Signed state cookie** | State, verifier and nonce ride in a short-lived (10 min) signed JWT in an HttpOnly cookie instead of server memory — so authorize and callback may land on **different replicas**. |
| **`safe_next_path`** | Open redirect: only same-origin relative paths are honoured as the post-login destination. |
| **Verified-email requirement for account linking** | Account takeover: an SSO identity only attaches to an existing local account when the provider asserts the address is verified. |

GitHub is not an OIDC provider, so it has no `id_token`; there the access token is used
against the REST API and a **verified primary email** is required.

Identities are keyed on the provider's stable opaque `subject`, never the email, which
can be reassigned. A user may link several providers.

Optional `PIPEFORGE_OAUTH_ALLOWED_EMAIL_DOMAINS` restricts sign-up to your own domains.

**Registering the redirect URI** — with each provider, register exactly:

```
{PIPEFORGE_PUBLIC_BASE_URL}/api/auth/oauth/{google|microsoft|github}/callback
```

### Tokens

| Token | Lifetime | Where it lives | Revocable |
| --- | --- | --- | --- |
| Access | **15 min** | Browser memory only (never `localStorage`) | Yes — via `token_version` |
| Refresh | **14 days** | **HttpOnly** cookie, `SameSite=Lax`, path-scoped to `/api/auth` | Yes — tracked per `jti` |

* Access tokens carry `typ`, `role` and `ver`. The `typ` claim is checked on every
  request, so a refresh token cannot be replayed as an access token.
* Bumping `User.token_version` invalidates **every access token already issued** to that
  user — revocation without a hot denylist. It fires on password change, sign-out
  everywhere, role change, and admin deactivation.
* Refresh tokens **rotate on every use**. Only the `jti` is stored, so a database leak
  yields nothing redeemable.
* **Reuse detection**: tokens form a *family*. Presenting an already-rotated token only
  happens if it leaked, so the entire family is revoked immediately and the event is
  audited as `auth.refresh.reuse_detected`.
* Because the access token lives in memory, a page reload has no credential in hand — the
  SPA trades the HttpOnly cookie for a fresh access token via `POST /api/auth/refresh`.
  An XSS payload cannot read the refresh token at all.

`POST /api/auth/logout` revokes the presented token; `POST /api/auth/logout-all` revokes
every session and bumps `token_version`. `GET /api/auth/sessions` lists the caller's live
sign-ins.

## Authorization

Roles are ordered **viewer < user < admin** (`app/models.py:Role`):

| Role | Can |
| --- | --- |
| `viewer` | Read own datasets and runs |
| `user` | Full control of own resources (default) |
| `admin` | Everything, plus user management and the audit log |

`require_role(Role.ADMIN)` builds a dependency enforcing a minimum role; the whole
`/api/admin` router sits behind it. Denials are logged as `authz.denied`.

**Bootstrap** — `PIPEFORGE_BOOTSTRAP_ADMIN_EMAIL` names the first admin. If unset, the
first account to register becomes admin.

**Lockout guards** — an admin cannot demote or disable themselves, and the last active
admin cannot be removed.

**Per-user data isolation** — every dataset/run query filters by `owner_id`. Requesting
another user's dataset returns `404`, not `403`, so existence is never confirmed.

## Rate limiting

**slowapi**, keyed on **identity, not address**: `user:<id>` when the request carries a
valid access token, `ip:<addr>` otherwise. Keying on the user is what stops an
authenticated attacker from bypassing limits by rotating source IPs, while
unauthenticated traffic (login, register) still gets per-IP protection.

Defaults: 200/min global, 10/min auth, 30/min upload, 60/min agents. Breaches return
`429` with a `Retry-After` header; `X-RateLimit-*` headers let clients back off early.

Storage is in-memory for a single process, or **Redis**
(`PIPEFORGE_RATELIMIT_STORAGE=redis://...`) so limits are enforced **across all
replicas**. Behind the nginx gateway uvicorn runs with `--proxy-headers`, so the real
client IP (from `X-Forwarded-For`) is used, not the proxy's.

## Error handling

Every error — expected or not — returns one envelope:

```json
{
  "detail": "Human readable message",
  "error": {
    "type": "validation_error",
    "message": "Human readable message",
    "request_id": "3f2c9a…",
    "details": [{ "field": "password", "message": "String should have at least 12 characters" }]
  }
}
```

Handlers are registered for `HTTPException`, `RequestValidationError` (422 with a
per-field breakdown), `RateLimitExceeded` (429), `IntegrityError` (**409**, not a 500),
`SQLAlchemyError` (503), and a catch-all for `Exception`.

An unhandled exception logs the **full traceback server-side** and returns only a generic
message plus the `request_id` — no stack trace, no SQL, no internal detail reaches the
client. Because the catch-all runs outside the middleware stack, the request id and the
core hardening headers are applied directly by the error handler so 500s are never bare.

## Logging and audit

**Structured logging** (`app/logging_config.py`) — one JSON object per line, ready to
index. A request-id context variable is stamped onto every record produced while handling
a request, so a single failure traces end to end. `X-Request-ID` is honoured from the
gateway when present and always echoed on the response, which is what makes a
user-reported error id findable.

**Audit trail** (`app/audit.py`) — security events are written to *both* the log stream
and the append-only `audit_log` table, so they survive a database outage and stay
queryable. Recorded: registration, login success/failure, logout, refresh success/failure,
**refresh reuse**, every SSO step, role changes, activation/deactivation, session
revocation, and dataset upload/delete. Each row carries actor, target, outcome, client IP,
user agent, and request id.

Admins query it at `GET /api/admin/audit` (filter by event prefix, actor, or outcome), or
in the UI at **/admin → Audit log**. Auditing never fails a request: database errors there
are swallowed and logged.

## Input validation

- All request bodies are **Pydantic v2** models with `extra="forbid"` — unknown fields are
  rejected, not silently ignored.
- Enums (`TaskType`) and field constraints (`min_length`, regex patterns) reject malformed
  input at the boundary; a model-level validator enforces cross-field rules.
- Uploads are validated by extension and **streamed with a hard size cap**
  (`PIPEFORGE_MAX_UPLOAD_BYTES`, default 200 MB) to prevent memory exhaustion; parse
  failures are caught and the partial file removed.

## Transport and headers

Set on every response by `SecurityHeadersMiddleware`:

`X-Content-Type-Options: nosniff` · `X-Frame-Options: DENY` · `Referrer-Policy: no-referrer` ·
`Cross-Origin-Opener-Policy: same-origin` · `X-Permitted-Cross-Domain-Policies: none` ·
`Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()` ·
`Content-Security-Policy` (deny-all for JSON; a scoped policy for the generated HTML
report, which is self-contained but needs inline script/style) · `Strict-Transport-Security`
when `PIPEFORGE_REFRESH_COOKIE_SECURE=true`.

**CORS** is restricted to configured origins with explicit method and header allow-lists;
credentials are enabled because of the refresh cookie. In the Docker topology the SPA and
API are same-origin through nginx, so CORS is effectively closed.

**No credentials in URLs.** The old `?token=` query fallback was removed — it leaked
credentials into browser history, referrer headers, and proxy access logs. Model downloads
and the EDA report are now fetched with the `Authorization` header and opened as blobs.

## File storage

Uploaded files are stored under a **sharded, non-guessable key** (`uuid4` + extension)
rather than the user-supplied filename, avoiding path traversal and hot directories.

## Schema management

Production applies schema changes with **Alembic** (`alembic upgrade head`, run by the
container entrypoint), not `create_all`. Set `PIPEFORGE_AUTO_CREATE_TABLES=false` outside
development. See [DEPLOYMENT.md](DEPLOYMENT.md#database-migrations).

## Container hardening

The backend image runs as a **non-root** user (uid 10001), ships a `HEALTHCHECK`, and
applies migrations before serving.

## Startup configuration audit

On boot the app warns about anything unsafe for production: a default or short
`PIPEFORGE_JWT_SECRET`, in-process rate-limit storage, a non-`Secure` refresh cookie, and
wildcard CORS. Watch for `startup.insecure_config` in the logs.

## Hardening checklist for production

- [ ] Set a strong `PIPEFORGE_JWT_SECRET` (≥32 bytes) and rotate periodically.
- [ ] Set `PIPEFORGE_REFRESH_COOKIE_SECURE=true` (enables HSTS) and terminate TLS at the ingress.
- [ ] Set `PIPEFORGE_PUBLIC_BASE_URL` to the real public origin — OAuth redirect URIs derive from it.
- [ ] Use Postgres + Redis (not SQLite / in-memory limits).
- [ ] Set `PIPEFORGE_AUTO_CREATE_TABLES=false`; run `alembic upgrade head`.
- [ ] Set `PIPEFORGE_BOOTSTRAP_ADMIN_EMAIL` so the first admin is deliberate.
- [ ] Restrict SSO with `PIPEFORGE_OAUTH_ALLOWED_EMAIL_DOMAINS` if this is an internal deployment.
- [ ] Ship JSON logs to a searchable store and alert on `auth.refresh.reuse_detected`, `authz.denied`, and `http.unhandled_exception`.
- [ ] Gate `/api/docs` and `/api/openapi.json` at the ingress if internet-facing.
- [ ] Put the storage volume on durable, backed-up object storage.
- [ ] Scan images and pin dependency versions.

Generate a secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
