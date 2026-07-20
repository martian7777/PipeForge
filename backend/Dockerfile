# PipeForge backend image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for pandas/pyarrow wheels are already bundled; keep the image slim.
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt

# Copy application code.
COPY app ./app

# Storage is mounted as a shared volume in production so every replica sees the
# same uploaded files and artifacts.
RUN mkdir -p /app/storage
VOLUME ["/app/storage"]

EXPOSE 8000

# Multiple worker processes per replica; scale replicas horizontally behind nginx.
# --proxy-headers makes the real client IP available (for per-client rate limiting).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
