"""add node integration schedules and external task snapshots

Revision ID: 0026_integration_schedules
Revises: 0025_workflow_node_models
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_integration_schedules"
down_revision: str | None = "0025_workflow_node_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_nodes",
        sa.Column("integration_mode", sa.String(20), nullable=False, server_default="webhook"),
    )
    op.add_column(
        "workflow_nodes",
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
    )
    op.add_column(
        "workflow_nodes",
        sa.Column("filter_assignee_id", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "workflow_nodes",
        sa.Column("filter_state_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "workflow_nodes",
        sa.Column("integration_sync_status", sa.String(30), nullable=False, server_default="IDLE"),
    )
    op.add_column("workflow_nodes", sa.Column("integration_sync_error", sa.Text()))
    op.add_column(
        "workflow_nodes", sa.Column("integration_last_synced_at", sa.DateTime(timezone=True))
    )
    op.create_table(
        "external_task_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("identifier", sa.String(100), nullable=False),
        sa.Column("assignee_id", sa.String(255)),
        sa.Column("state_id", sa.String(255)),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("synchronized_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_external_task_provider_id"),
    )


def downgrade() -> None:
    op.drop_table("external_task_snapshots")
    op.drop_column("workflow_nodes", "integration_last_synced_at")
    op.drop_column("workflow_nodes", "integration_sync_error")
    op.drop_column("workflow_nodes", "integration_sync_status")
    op.drop_column("workflow_nodes", "filter_state_ids")
    op.drop_column("workflow_nodes", "filter_assignee_id")
    op.drop_column("workflow_nodes", "poll_interval_seconds")
    op.drop_column("workflow_nodes", "integration_mode")
