"""add estimated worker run cost

Revision ID: 0017_worker_run_cost
Revises: 0016_finding_occurrences
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_worker_run_cost"
down_revision: str | None = "0016_finding_occurrences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_runs",
        sa.Column("estimated_cost_usd", sa.Numeric(14, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("worker_runs", "estimated_cost_usd")
