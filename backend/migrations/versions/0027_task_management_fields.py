"""add provider-neutral task management timestamps

Revision ID: 0027_task_management_fields
Revises: 0026_integration_schedules
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_task_management_fields"
down_revision: str | None = "0026_integration_schedules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("due_at", sa.DateTime(timezone=True)))
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_tasks_state_priority", "tasks", ["state", "priority"])
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_due_at", table_name="tasks")
    op.drop_index("ix_tasks_state_priority", table_name="tasks")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "started_at")
    op.drop_column("tasks", "due_at")
