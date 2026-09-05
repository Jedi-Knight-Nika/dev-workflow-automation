"""add execution policy approvals and tool audit

Revision ID: 0033_execution_policy_gateway
Revises: 0032_manual_task_properties
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_execution_policy_gateway"
down_revision: str | None = "0032_manual_task_properties"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("mode", sa.String(30), nullable=False, server_default="AUTONOMOUS"),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("approved_hosts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "max_command_timeout_seconds", sa.Integer(), nullable=False, server_default="1200"
        ),
        sa.Column("max_output_bytes", sa.Integer(), nullable=False, server_default="1000000"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        "INSERT INTO execution_policies (id, team_id) SELECT gen_random_uuid(), id FROM teams"
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
        ),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("resolution_scope", sa.String(30)),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approval_pending", "approval_requests", ["state", "expires_at"])
    op.create_table(
        "tool_execution_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "worker_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("worker_runs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="SET NULL")
        ),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("policy_rule", sa.String(255), nullable=False),
        sa.Column("arguments_sanitized", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_tool_events_task_created", "tool_execution_events", ["task_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("tool_execution_events")
    op.drop_table("approval_requests")
    op.drop_table("execution_policies")
