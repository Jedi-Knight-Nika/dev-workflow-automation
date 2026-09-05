"""add durable webhook delivery inbox"""

import sqlalchemy as sa
from alembic import op

revision = "0004_github_webhooks"
down_revision = "0003_provider_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("delivery_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100)),
        sa.Column("repository_external_id", sa.String(255)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "delivery_id", name="uq_webhook_provider_delivery"),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
