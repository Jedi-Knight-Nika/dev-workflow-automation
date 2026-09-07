"""record task message edits

Revision ID: 0053_task_message_edits
Revises: 0052_task_message_threads
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_task_message_edits"
down_revision: str | None = "0052_task_message_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task_messages", sa.Column("edited_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("task_messages", "edited_at")
