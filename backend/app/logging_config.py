"""Structured logging.

Every log line is emitted as a single JSON object (``PIPEFORGE_LOG_FORMAT=json``, the
default) so a log shipper can index it without regex parsing. The request id, and the
authenticated user id when known, are carried in context variables and stamped onto
every record produced while handling that request -- including logs written deep inside
the pipeline -- so a single failure can be traced end to end.

Set ``PIPEFORGE_LOG_FORMAT=console`` for human-readable local development output.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from .config import settings

# Carried across the whole request, including into thread-pool jobs that copy context.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[int | None] = ContextVar("user_id", default=None)

# Attributes present on every LogRecord; anything else was passed via ``extra=`` and
# therefore belongs in the structured payload.
_STANDARD_ATTRS = frozenset(
    """args asctime created exc_info exc_text filename funcName levelname levelno lineno
    module msecs message msg name pathname process processName relativeCreated stack_info
    thread threadName taskName""".split()
)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        user_id = user_id_ctx.get()
        if user_id is not None:
            payload["user_id"] = user_id

        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Readable single-line output for local development."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = request_id_ctx.get()
        return f"{base}  [req={request_id[:8]}]" if request_id else base


def configure_logging() -> None:
    """Install the root handler. Idempotent -- safe to call from tests and workers."""
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            ConsoleFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # uvicorn ships its own handlers; drop them so everything flows through ours once.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    # Our own access middleware logs richer lines than uvicorn's; silence the duplicate.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
