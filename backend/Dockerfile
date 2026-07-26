# PipeForge backend image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for pandas/pyarrow wheels are already bundled; keep the image slim.
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt

# Copy application code and the migration scripts.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Storage is mounted as a shared volume in production so every replica sees the
# same uploaded files and artifacts.
RUN mkdir -p /app/storage

# Drop root: the app only ever needs to read its code and write to /app/storage.
RUN useradd --create-home --uid 10001 pipeforge \
 && chown -R pipeforge:pipeforge /app
USER pipeforge

VOLUME ["/app/storage"]

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# The entrypoint applies database migrations before serving.
ENTRYPOINT ["./docker-entrypoint.sh"]

# Multiple worker processes per replica; scale replicas horizontally behind nginx.
# --proxy-headers makes the real client IP available (for per-client rate limiting
# and audit records), trusting only the gateway in front of us.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
