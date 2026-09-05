"""track repeated review findings

Revision ID: 0016_finding_occurrences
Revises: 0015_context_pending_state
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_finding_occurrences"
down_revision: str | None = "0015_context_pending_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_findings", sa.Column("finding_fingerprint", sa.String(64)))
    op.add_column(
        "review_findings",
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("review_findings", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_review_findings_fingerprint",
        "review_findings",
        ["task_id", "finding_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_findings_fingerprint", table_name="review_findings")
    op.drop_column("review_findings", "last_seen_at")
    op.drop_column("review_findings", "occurrence_count")
    op.drop_column("review_findings", "finding_fingerprint")
