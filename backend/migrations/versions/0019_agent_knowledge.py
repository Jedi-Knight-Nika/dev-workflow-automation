"""agent-scoped manual knowledge

Revision ID: 0019_agent_knowledge
Revises: 0018_webhook_delivery_processing
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_agent_knowledge"
down_revision: str | None = "0018_webhook_delivery_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    job_role = postgresql.ENUM(
        "INTAKE", "THINKER", "EXECUTOR", "REVIEWER", name="jobrole", create_type=False
    )
    op.create_table(
        "agent_knowledge_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role", job_role, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("agent_knowledge_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", job_role, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "ALTER TABLE agent_knowledge_chunks ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    op.create_index("ix_agent_knowledge_chunks_role", "agent_knowledge_chunks", ["role"])
    op.execute(
        "CREATE INDEX ix_agent_knowledge_chunks_embedding ON agent_knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20)"
    )


def downgrade() -> None:
    op.drop_table("agent_knowledge_chunks")
    op.drop_table("agent_knowledge_sources")
