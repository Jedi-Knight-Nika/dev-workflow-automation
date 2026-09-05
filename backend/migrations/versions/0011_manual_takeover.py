"""durable manual takeover state

Revision ID: 0011_manual_takeover
Revises: 0010_review_findings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_manual_takeover"
down_revision: str | None = "0010_review_findings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("manual_takeover", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tasks", "manual_takeover")
