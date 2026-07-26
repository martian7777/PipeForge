#!/bin/sh
# Apply schema migrations, then hand off to the CMD (uvicorn).
#
# Every replica runs this on start. Alembic takes a lock on the version table, so
# concurrent replicas serialize: the first applies the migrations, the rest see the
# database is already at head and continue. That makes `docker compose up --scale
# backend=N` safe without a separate migration job.
set -e

echo "[entrypoint] applying database migrations"
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
