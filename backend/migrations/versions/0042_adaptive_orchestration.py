"""persist adaptive orchestration state

Revision ID: 0042_adaptive_orchestration
Revises: 0041_account_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_adaptive_orchestration"
down_revision: str | None = "0041_account_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("execution_profile", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("execution_strategy", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("progress_fingerprint", sa.JSON(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("no_progress_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tasks", "no_progress_count")
    op.drop_column("tasks", "progress_fingerprint")
    op.drop_column("tasks", "execution_strategy")
    op.drop_column("tasks", "execution_profile")
