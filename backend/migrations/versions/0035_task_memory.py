"""add persistent task memory checkpoints and context audit

Revision ID: 0035_task_memory
Revises: 0034_notifications_incidents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_task_memory"
down_revision: str | None = "0034_notifications_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "task_memories",
        sa.Column(
            "task_id", uuid_type, sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("known_facts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("decisions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rejected_approaches", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("invariants", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("important_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("important_symbols", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("open_questions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("open_finding_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resolved_finding_summaries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("current_plan_job_id", uuid_type, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("current_sha", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        "INSERT INTO task_memories (task_id, goal, current_sha) SELECT id, title, current_revision FROM tasks"
    )
    op.create_table(
        "agent_checkpoints",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "task_id", uuid_type, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("agent_id", uuid_type, sa.ForeignKey("ai_agents.id", ondelete="SET NULL")),
        sa.Column("role_id", uuid_type, sa.ForeignKey("roles.id", ondelete="SET NULL")),
        sa.Column("role", postgresql.ENUM(name="jobrole", create_type=False), nullable=False),
        sa.Column("checkpoint_type", sa.String(50), nullable=False),
        sa.Column("repository_sha", sa.String(64)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("token_estimate", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_checkpoints_task_role_created", "agent_checkpoints", ["task_id", "role", "created_at"]
    )
    op.create_table(
        "job_contexts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("compiler_version", sa.String(30), nullable=False),
        sa.Column("task_memory_version", sa.Integer()),
        sa.Column("repository_sha", sa.String(64)),
        sa.Column("checkpoint_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("plan_job_id", uuid_type, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("finding_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rag_chunk_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("compilation_duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("job_contexts")
    op.drop_table("agent_checkpoints")
    op.drop_table("task_memories")
