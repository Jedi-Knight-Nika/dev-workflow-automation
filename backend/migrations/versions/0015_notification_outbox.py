"""Optional notification transport; task state remains authoritative."""

import sqlalchemy as sa
from alembic import op

revision = "0015_notification_outbox"
down_revision = "0014_task_creation_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(100)),
    )
    op.create_index("ix_notification_due", "notification_outbox", ["published_at", "available_at"])


def downgrade() -> None:
    op.drop_table("notification_outbox")
