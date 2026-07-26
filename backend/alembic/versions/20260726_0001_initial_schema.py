"""Initial schema: users, datasets, runs, model results, and the agent tables.

This mirrors the schema that ``Base.metadata.create_all`` produced before migrations
were introduced. An existing database created by ``create_all`` should be marked as
already at this revision rather than re-running it::

    alembic stamp 0001
    alembic upgrade head

Revision ID: 0001
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT NULL mirrors the ORM: every one of these columns has a Python-side default,
    # so the application always supplies a value. Keeping the constraint in the database
    # means a bad write fails loudly instead of silently storing NULL.
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("file_format", sa.String(length=32), nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=False),
        sa.Column("n_cols", sa.Integer(), nullable=False),
        sa.Column("schema", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_datasets_owner_id", "datasets", ["owner_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("target_col", sa.String(length=512), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("best_model_id", sa.Integer(), nullable=True),
        sa.Column("eda", sa.JSON(), nullable=False),
        sa.Column("report_path", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "model_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("plots", sa.JSON(), nullable=False),
        sa.Column("artifact_path", sa.String(length=1024), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
    )

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_agent", sa.String(length=64), nullable=True),
        sa.Column("error", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("tool_args", sa.JSON(), nullable=False),
        sa.Column("tool_result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"])

    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("proposed_config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_proposals_session_id", "agent_proposals", ["session_id"])

    op.create_table(
        "agent_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=True),
    )
    op.create_index("ix_agent_configs_user_id", "agent_configs", ["user_id"])


def downgrade() -> None:
    op.drop_table("agent_configs")
    op.drop_table("agent_proposals")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")
    op.drop_table("model_results")
    op.drop_table("runs")
    op.drop_table("datasets")
    op.drop_table("users")
