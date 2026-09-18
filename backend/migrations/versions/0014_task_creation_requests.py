"""Persist idempotent task creation without changing existing tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0014_task_creation_requests"
down_revision = "0013_deployment_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_creation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
    )
    op.create_index("ix_task_creation_requests_task_id", "task_creation_requests", ["task_id"])


def downgrade() -> None:
    op.drop_table("task_creation_requests")
