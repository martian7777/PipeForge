"""Authentication and authorization primitives.

* **Passwords** -- bcrypt with a per-password salt.
* **Access tokens** -- short-lived (15 min) stateless JWTs. They carry the user's role
  and ``token_version``; bumping ``User.token_version`` invalidates every access token
  already issued to that user, so we get revocation without a hot denylist.
* **Refresh tokens** -- long-lived JWTs whose ``jti`` is tracked in ``refresh_tokens``.
  Every use *rotates* the token: the presented one is revoked and a new one issued.
  Presenting an already-rotated token means it leaked, so the entire token family is
  revoked (reuse detection).
* **RBAC** -- ``require_role(Role.ADMIN)`` builds a dependency that enforces a minimum
  role, ordered viewer < user < admin.

Everything is stateless apart from the refresh-token table, so the API scales across
replicas behind a load balancer with no sticky sessions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .logging_config import get_logger, user_id_ctx
from .models import RefreshToken, Role, User

logger = get_logger(__name__)

# auto_error=False so a missing header yields our own 401 shape, not FastAPI's.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ACCESS = "access"
REFRESH = "refresh"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False  # SSO-only account: no local password to check against
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# --- Token minting -----------------------------------------------------------


def create_access_token(user: User, extra: dict[str, Any] | None = None) -> str:
    now = _utcnow()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "typ": ACCESS,
        "role": user.role,
        "ver": user.token_version,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _encode_refresh(user_id: int, jti: str, family_id: str, expires_at: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "typ": REFRESH,
            "jti": jti,
            "fam": family_id,
            "iat": _utcnow(),
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def issue_refresh_token(
    db: Session,
    user: User,
    request: Request | None = None,
    family_id: str | None = None,
) -> str:
    """Mint a refresh token and record its jti. Starts a new family unless one is given."""
    jti = uuid.uuid4().hex
    family = family_id or uuid.uuid4().hex
    expires_at = _utcnow() + timedelta(days=settings.refresh_token_ttl_days)

    db.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            family_id=family,
            expires_at=expires_at,
            user_agent=(request.headers.get("user-agent") if request else None),
            client_ip=(client_ip(request) if request else None),
        )
    )
    db.commit()
    return _encode_refresh(user.id, jti, family, expires_at)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Verify signature and expiry, and optionally assert the token's ``typ`` claim.

    The type check is what stops a refresh token being replayed as an access token.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if expected_type and payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return payload


# --- Refresh rotation and revocation ----------------------------------------


class RefreshError(Exception):
    """A refresh token was missing, expired, malformed, revoked, or replayed."""

    def __init__(self, message: str, *, reuse_detected: bool = False) -> None:
        super().__init__(message)
        self.reuse_detected = reuse_detected


def revoke_family(db: Session, family_id: str, reason: str) -> int:
    """Revoke every live token in a family. Returns how many were revoked."""
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow(), revoked_reason=reason)
    )
    db.commit()
    return int(result.rowcount or 0)


def revoke_all_for_user(db: Session, user: User, reason: str = "logout_all") -> int:
    """Sign the user out everywhere: kill all refresh tokens and all access tokens."""
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow(), revoked_reason=reason)
    )
    user.token_version += 1  # invalidates outstanding access tokens immediately
    db.commit()
    return int(result.rowcount or 0)


def revoke_refresh_token(db: Session, token: str, reason: str = "logout") -> None:
    """Best-effort revocation of a single presented token (used by logout)."""
    try:
        payload = decode_token(token, REFRESH)
    except jwt.PyJWTError:
        return
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload.get("jti", "")))
    if row is not None and row.revoked_at is None:
        row.revoked_at = _utcnow()
        row.revoked_reason = reason
        db.commit()


def rotate_refresh_token(db: Session, token: str, request: Request | None = None) -> tuple[str, str, User]:
    """Exchange a refresh token for a fresh (access, refresh) pair.

    Raises ``RefreshError``. If the presented token was already rotated away, the whole
    family is revoked -- that pattern only happens when a token has been stolen.
    """
    try:
        payload = decode_token(token, REFRESH)
    except jwt.PyJWTError as exc:
        raise RefreshError("Invalid or expired refresh token") from exc

    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload.get("jti", "")))
    if row is None:
        raise RefreshError("Unknown refresh token")

    if row.revoked_at is not None:
        revoked = revoke_family(db, row.family_id, "reuse_detected")
        logger.warning(
            "refresh token reuse detected; revoked family",
            extra={
                "event": "auth.refresh.reuse_detected",
                "user_id": row.user_id,
                "family_id": row.family_id,
                "revoked_count": revoked,
            },
        )
        raise RefreshError("Refresh token has already been used", reuse_detected=True)

    if not row.is_active:
        raise RefreshError("Refresh token expired")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise RefreshError("Account is inactive")

    new_refresh = issue_refresh_token(db, user, request, family_id=row.family_id)
    row.revoked_at = _utcnow()
    row.revoked_reason = "rotated"
    row.replaced_by_jti = decode_token(new_refresh, REFRESH)["jti"]
    db.commit()

    return create_access_token(user), new_refresh, user


def purge_expired_refresh_tokens(db: Session) -> int:
    """Drop rows that expired long ago. Called on startup; safe to run any time."""
    cutoff = _utcnow() - timedelta(days=settings.refresh_token_ttl_days)
    rows = db.query(RefreshToken).filter(RefreshToken.expires_at < cutoff).delete()
    db.commit()
    return int(rows or 0)


# --- Request helpers ---------------------------------------------------------


def client_ip(request: Request | None) -> str | None:
    """Real client IP, honouring the gateway's X-Forwarded-For."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# --- Dependencies ------------------------------------------------------------

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve and return the authenticated user, or raise 401.

    Bearer header only -- the previous ``?token=`` query fallback was removed because it
    leaks credentials into browser history, referrer headers, and proxy access logs. The
    frontend now fetches downloads and reports with the header and opens them as blobs.
    """
    if not token:
        raise _credentials_exc

    try:
        payload = decode_token(token, ACCESS)
        user_id = int(payload.get("sub", ""))
    except (jwt.PyJWTError, ValueError):
        raise _credentials_exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc

    # Reject tokens minted before the last "sign out everywhere" / role change.
    if int(payload.get("ver", -1)) != user.token_version:
        raise _credentials_exc

    user_id_ctx.set(user.id)
    request.state.user = user
    return user


def optional_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Like ``current_user`` but returns None instead of raising. For public routes."""
    try:
        return current_user(request, token, db)
    except HTTPException:
        return None


def require_role(minimum: str) -> Callable[..., User]:
    """Build a dependency asserting the caller holds at least ``minimum``.

    Usage::

        @router.get("/users", dependencies=[Depends(require_role(Role.ADMIN))])
    """

    def _dependency(user: User = Depends(current_user)) -> User:
        if Role.rank(user.role) < Role.rank(minimum):
            logger.warning(
                "authorization denied",
                extra={
                    "event": "authz.denied",
                    "user_id": user.id,
                    "role": user.role,
                    "required_role": minimum,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires the '{minimum}' role or higher",
            )
        return user

    return _dependency


require_admin = require_role(Role.ADMIN)
require_user = require_role(Role.USER)
