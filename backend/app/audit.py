"""Audit trail for security-relevant events.

Every call writes two places: a structured log line (so events reach the log pipeline
even if the database is down) and an append-only ``audit_log`` row (so they are
queryable from the admin API). Auditing must never break the request it describes, so
database failures here are swallowed and logged.

Event names are dotted and hierarchical -- ``auth.login.success``, ``admin.role.changed``,
``dataset.deleted`` -- so they can be filtered by prefix.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .config import settings
from .logging_config import get_logger, request_id_ctx
from .models import AuditLog, User
from .security import client_ip

logger = get_logger("audit")

# --- Event name constants (use these rather than raw strings) ---
LOGIN_SUCCESS = "auth.login.success"
LOGIN_FAILURE = "auth.login.failure"
REGISTER = "auth.register"
LOGOUT = "auth.logout"
LOGOUT_ALL = "auth.logout_all"
REFRESH_SUCCESS = "auth.refresh.success"
REFRESH_FAILURE = "auth.refresh.failure"
REFRESH_REUSE = "auth.refresh.reuse_detected"
OAUTH_START = "auth.oauth.start"
OAUTH_SUCCESS = "auth.oauth.success"
OAUTH_FAILURE = "auth.oauth.failure"
OAUTH_LINKED = "auth.oauth.linked"
ROLE_CHANGED = "admin.role.changed"
USER_DEACTIVATED = "admin.user.deactivated"
USER_ACTIVATED = "admin.user.activated"
USER_SESSIONS_REVOKED = "admin.user.sessions_revoked"
DATASET_UPLOADED = "dataset.uploaded"
DATASET_DELETED = "dataset.deleted"


def record(
    db: Session | None,
    event: str,
    *,
    request: Request | None = None,
    actor: User | None = None,
    actor_email: str | None = None,
    target: str | None = None,
    outcome: str = "success",
    **detail: Any,
) -> None:
    """Log and persist one audit event."""
    ip = client_ip(request)
    user_agent = request.headers.get("user-agent") if request else None
    request_id = request_id_ctx.get()

    log = logger.info if outcome == "success" else logger.warning
    log(
        event,
        extra={
            "event": event,
            "outcome": outcome,
            "actor_user_id": actor.id if actor else None,
            "actor_email": actor.email if actor else actor_email,
            "target": target,
            "client_ip": ip,
            **detail,
        },
    )

    if not settings.audit_to_db or db is None:
        return

    try:
        db.add(
            AuditLog(
                event=event,
                actor_user_id=actor.id if actor else None,
                actor_email=actor.email if actor else actor_email,
                target=target,
                outcome=outcome,
                client_ip=ip,
                user_agent=(user_agent or "")[:512] or None,
                request_id=request_id,
                detail_json=detail or {},
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - auditing must never fail the request
        db.rollback()
        logger.exception("failed to persist audit event", extra={"event": event})
