"""persist notification retry schedule

Revision ID: 0048_notification_retry_schedule
Revises: 0047_repository_archival
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_notification_retry_schedule"
down_revision: str | None = "0047_repository_archival"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_notification_deliveries_retry_due",
        "notification_deliveries",
        ["channel", "state", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_retry_due",
        table_name="notification_deliveries",
    )
    op.drop_column("notification_deliveries", "next_attempt_at")
