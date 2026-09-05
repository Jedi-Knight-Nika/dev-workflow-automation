"""durable internal review findings

Revision ID: 0010_review_findings
Revises: 0009_repository_index_error
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_review_findings"
down_revision: str | None = "0009_repository_index_error"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "reviewer_job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_fingerprint", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_findings_task_status", "review_findings", ["task_id", "status"])


def downgrade() -> None:
    op.drop_table("review_findings")
