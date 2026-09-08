"""Independent read-only companion history; no changes to engineering tables."""

import sqlalchemy as sa
from alembic import op

revision = "0007_observer"
down_revision = "0006_canonical_identifiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observer_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(200), nullable=False, unique=True),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("team_id", sa.Uuid()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("snoozed_until", sa.DateTime(timezone=True)),
        sa.Column("rule_version", sa.String(32), nullable=False),
    )
    op.create_index("ix_observer_events_status", "observer_events", ["status"])
    op.create_table(
        "observer_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_observer_conversation_owner", "observer_conversations", ["owner", "updated_at"]
    )
    op.create_table(
        "observer_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("observer_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_observer_message_conversation", "observer_messages", ["conversation_id", "created_at"]
    )
    op.create_table(
        "observer_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("observer_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("message", sa.String(2000), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_observer_questions_owner", "observer_questions", ["owner"])
    op.create_table(
        "observer_preferences",
        sa.Column("owner", sa.String(64), primary_key=True),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "observer_model_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("observer_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for name in (
        "observer_model_runs",
        "observer_preferences",
        "observer_questions",
        "observer_messages",
        "observer_conversations",
        "observer_events",
    ):
        op.drop_table(name)
