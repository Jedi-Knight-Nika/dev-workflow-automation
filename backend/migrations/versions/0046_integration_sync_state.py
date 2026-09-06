"""add generic integration synchronization state

Revision ID: 0046_integration_sync_state
Revises: 0045_resilience_state
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_integration_sync_state"
down_revision: str | None = "0045_resilience_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column("sync_status", sa.String(30), nullable=False, server_default="IDLE"),
    )
    op.add_column(
        "integrations", sa.Column("last_synced_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_integrations_sync_due",
        "integrations",
        ["provider_name", "sync_status", "last_synced_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integrations_sync_due", table_name="integrations")
    op.drop_column("integrations", "last_synced_at")
    op.drop_column("integrations", "sync_status")
