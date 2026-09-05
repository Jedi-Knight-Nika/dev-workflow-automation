"""add notifications incidents and telegram connection

Revision ID: 0034_notifications_incidents
Revises: 0033_execution_policy_gateway
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_notifications_incidents"
down_revision: str | None = "0033_execution_policy_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("fingerprint", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("integration_id", UUID, sa.ForeignKey("integrations.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_incidents_status_severity", "incidents", ["status", "severity"])
    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False, server_default="local-user"),
        sa.Column("incident_id", UUID, sa.ForeignKey("incidents.id", ondelete="SET NULL")),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="UNREAD"),
        sa.Column("action_type", sa.String(80)),
        sa.Column("action_target", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_user_status", "notifications", ["user_id", "status"])
    op.create_table(
        "notification_deliveries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "notification_id",
            UUID,
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("recipient_ref", sa.String(255), nullable=False),
        sa.Column("state", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("external_message_id", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "telegram_connection_tokens",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "telegram_connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False, unique=True),
        sa.Column("telegram_user_id", sa.String(40), nullable=False),
        sa.Column("telegram_chat_id", sa.String(40), nullable=False, unique=True),
        sa.Column("telegram_username", sa.String(255)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "connected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True)),
        sa.Column("last_delivery_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("telegram_updates")
    op.drop_table("telegram_connections")
    op.drop_table("telegram_connection_tokens")
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")
    op.drop_table("incidents")
