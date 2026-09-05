"""track durable webhook processing

Revision ID: 0018_webhook_delivery_processing
Revises: 0017_worker_run_cost
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_webhook_delivery_processing"
down_revision: str | None = "0017_worker_run_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_deliveries",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("webhook_deliveries", sa.Column("last_error", sa.Text()))
    op.add_column("webhook_deliveries", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_webhook_deliveries_pending",
        "webhook_deliveries",
        ["provider", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_pending", table_name="webhook_deliveries")
    op.drop_column("webhook_deliveries", "processed_at")
    op.drop_column("webhook_deliveries", "last_error")
    op.drop_column("webhook_deliveries", "attempts")
