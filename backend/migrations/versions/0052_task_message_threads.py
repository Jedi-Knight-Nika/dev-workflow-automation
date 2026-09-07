"""add task message threads and soft deletion

Revision ID: 0052_task_message_threads
Revises: 0051_task_conversation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_task_message_threads"
down_revision: str | None = "0051_task_conversation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task_messages", sa.Column("reply_to_id", sa.BigInteger()))
    op.add_column("task_messages", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_task_messages_reply_to_id",
        "task_messages",
        "task_messages",
        ["reply_to_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_task_messages_reply_to_id", "task_messages", ["reply_to_id"])


def downgrade() -> None:
    op.drop_index("ix_task_messages_reply_to_id", table_name="task_messages")
    op.drop_constraint("fk_task_messages_reply_to_id", "task_messages", type_="foreignkey")
    op.drop_column("task_messages", "deleted_at")
    op.drop_column("task_messages", "reply_to_id")
