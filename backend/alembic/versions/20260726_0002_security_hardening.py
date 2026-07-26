"""Security hardening: RBAC, SSO identities, refresh tokens, audit log.

* ``users`` gains ``role``, ``token_version``, ``last_login_at`` and profile fields, and
  ``password_hash`` becomes nullable so SSO-only accounts are representable.
* ``oauth_identities`` links federated (provider, subject) pairs to local users.
* ``refresh_tokens`` tracks issued refresh tokens so they can be rotated and revoked.
* ``audit_log`` is the append-only record of security events.

The first existing user is promoted to admin so the deployment is not left without one.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users -----------------------------------------------------------
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("full_name", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("avatar_url", sa.String(length=1024), nullable=True))
        batch.add_column(
            sa.Column("role", sa.String(length=16), nullable=False, server_default="user")
        )
        batch.add_column(
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        # SSO-only accounts have no local password.
        batch.alter_column("password_hash", existing_type=sa.String(length=256), nullable=True)
    op.create_index("ix_users_role", "users", ["role"])

    # Without this the upgrade would leave an existing deployment with zero admins.
    op.execute(
        "UPDATE users SET role = 'admin' "
        "WHERE id = (SELECT MIN(id) FROM users) AND NOT EXISTS "
        "(SELECT 1 FROM users WHERE role = 'admin')"
    )

    # --- oauth_identities -------------------------------------------------
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])

    # --- refresh_tokens ---------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(length=32), nullable=True),
        sa.Column("replaced_by_jti", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    # --- audit_log --------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("target", sa.String(length=256), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_log_event", "audit_log", ["event"])
    op.create_index("ix_audit_log_request_id", "audit_log", ["request_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_actor_created", "audit_log", ["actor_user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("refresh_tokens")
    op.drop_table("oauth_identities")
    op.drop_index("ix_users_role", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=256), nullable=False)
        batch.drop_column("last_login_at")
        batch.drop_column("token_version")
        batch.drop_column("role")
        batch.drop_column("avatar_url")
        batch.drop_column("full_name")
