"""add internal task conversation

Revision ID: 0051_task_conversation
Revises: 0050_repository_scope_runtime
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_task_conversation"
down_revision: str | None = "0050_repository_scope_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("author_type", sa.String(20), nullable=False),
        sa.Column("author_name", sa.String(120), nullable=False),
        sa.Column("author_role", sa.String(30)),
        sa.Column("kind", sa.String(30), nullable=False, server_default="COMMENT"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["ai_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_task_messages_agent_id", "task_messages", ["agent_id"])
    op.create_index("ix_task_messages_task_id_id", "task_messages", ["task_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_task_messages_task_id_id", table_name="task_messages")
    op.drop_index("ix_task_messages_agent_id", table_name="task_messages")
    op.drop_table("task_messages")
