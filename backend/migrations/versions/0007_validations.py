"""revision-aware validation evidence

Revision ID: 0007_validations
Revises: 0006_pull_requests
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_validations"
down_revision: str | None = "0006_pull_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE taskstate ADD VALUE IF NOT EXISTS 'MERGED'")
    op.create_table(
        "validation_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("details_url", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_task_revision", "validation_records", ["task_id", "revision"])


def downgrade() -> None:
    op.drop_index("ix_validation_task_revision", table_name="validation_records")
    op.drop_table("validation_records")
