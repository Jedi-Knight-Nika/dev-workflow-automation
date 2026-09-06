"""add recoverable task archival

Revision ID: 0039_task_archival
Revises: 0038_workflow_revisions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_task_archival"
down_revision: str | None = "0038_workflow_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tasks_archived_at", "tasks", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_archived_at", table_name="tasks")
    op.drop_column("tasks", "archived_at")
