"""add durable resilience state

Revision ID: 0045_resilience_state
Revises: 0044_role_runtime_defaults
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_resilience_state"
down_revision: str | None = "0044_role_runtime_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for state in (
        "WAITING_PROVIDER",
        "WAITING_INTEGRATION",
        "WAITING_CONFIGURATION",
        "WAITING_HUMAN",
    ):
        op.execute(f"ALTER TYPE jobstate ADD VALUE IF NOT EXISTS '{state}'")

    op.add_column("incidents", sa.Column("root_resource_type", sa.String(40)))
    op.add_column("incidents", sa.Column("root_resource_id", sa.String(255)))
    op.create_table(
        "health_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="HEALTHY"),
        sa.Column("circuit_state", sa.String(20), nullable=False, server_default="CLOSED"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("next_probe_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_class", sa.String(80)),
        sa.Column("failure_fingerprint", sa.String(255)),
        sa.Column("probe_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_health_resource"),
    )
    op.create_index("ix_health_probe", "health_states", ["circuit_state", "next_probe_at"])
    op.create_table(
        "failure_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("resource_type", sa.String(40)),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("failure_class", sa.String(80), nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("safe_message", sa.Text(), nullable=False),
        sa.Column("technical_details_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_failure_events_job_created", "failure_events", ["job_id", "created_at"])
    op.create_index("ix_failure_events_fingerprint", "failure_events", ["fingerprint"])
    op.create_table(
        "job_retry_states",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("provider_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("integration_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("protocol_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engineering_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_fingerprint", sa.String(255)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("job_retry_states")
    op.drop_index("ix_failure_events_fingerprint", table_name="failure_events")
    op.drop_index("ix_failure_events_job_created", table_name="failure_events")
    op.drop_table("failure_events")
    op.drop_index("ix_health_probe", table_name="health_states")
    op.drop_table("health_states")
    op.drop_column("incidents", "root_resource_id")
    op.drop_column("incidents", "root_resource_type")
    # PostgreSQL enum values are intentionally retained on downgrade.
