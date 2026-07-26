"""Administrative endpoints. Every route requires the ``admin`` role.

Guard rails: an admin cannot demote, disable, or lock out *themselves*, and the last
remaining admin cannot be removed -- otherwise a single mis-click leaves the deployment
with no way back in.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import AuditLog, Role, User
from ..schemas import ActiveUpdate, AuditLogOut, RoleUpdate, UserOut
from ..security import require_admin, revoke_all_for_user

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def _admin_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(User.id)).where(User.role == Role.ADMIN, User.is_active.is_(True))
        )
        or 0
    )


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=320, description="Filter by email substring"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(
    user_id: int,
    body: RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> User:
    target = _get_user_or_404(db, user_id)

    if target.id == actor.id and body.role != Role.ADMIN:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
    if target.role == Role.ADMIN and body.role != Role.ADMIN and _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot demote the last active admin")

    previous, target.role = target.role, body.role
    # The role is baked into access tokens, so outstanding ones must stop being honoured.
    target.token_version += 1
    db.commit()
    db.refresh(target)

    audit.record(db, audit.ROLE_CHANGED, request=request, actor=actor,
                 target=target.email, previous_role=previous, new_role=target.role)
    return target


@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_active(
    user_id: int,
    body: ActiveUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> User:
    target = _get_user_or_404(db, user_id)

    if target.id == actor.id and not body.is_active:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if not body.is_active and target.role == Role.ADMIN and _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot disable the last active admin")

    target.is_active = body.is_active
    db.commit()

    if not body.is_active:
        # Disabling must take effect now, not whenever the access token happens to expire.
        revoke_all_for_user(db, target, reason="admin")
    db.refresh(target)

    audit.record(
        db,
        audit.USER_ACTIVATED if body.is_active else audit.USER_DEACTIVATED,
        request=request,
        actor=actor,
        target=target.email,
    )
    return target


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_sessions(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    """Force a user off every device (suspected credential compromise)."""
    target = _get_user_or_404(db, user_id)
    revoked = revoke_all_for_user(db, target, reason="admin")
    audit.record(db, audit.USER_SESSIONS_REVOKED, request=request, actor=actor,
                 target=target.email, revoked_count=revoked)


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit(
    db: Session = Depends(get_db),
    event_prefix: str | None = Query(default=None, max_length=64),
    actor_user_id: int | None = Query(default=None, ge=1),
    outcome: str | None = Query(default=None, pattern="^(success|failure)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLog]:
    """Query the audit trail, newest first."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    if event_prefix:
        stmt = stmt.where(AuditLog.event.startswith(event_prefix))
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    return list(db.scalars(stmt))
