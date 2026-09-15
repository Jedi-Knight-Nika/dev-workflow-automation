"""Activity relationships and explicit file collection state; business tables are unchanged."""

from alembic import op

revision = "0010_activity_details"
down_revision = "0009_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE activity_events ADD COLUMN source_references JSONB NOT NULL DEFAULT '[]'"
    )
    op.execute("ALTER TABLE activity_events ADD COLUMN file_status VARCHAR(24)")
    op.execute("ALTER TABLE activity_events ADD COLUMN file_attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE activity_events ADD COLUMN file_retry_at TIMESTAMP WITH TIME ZONE")
    op.execute(
        "UPDATE activity_events SET file_status = 'COMPLETE', file_checked_at = recorded_at WHERE file_checked_at > '9000-01-01'"
    )
    op.execute(
        "CREATE INDEX ix_activity_references ON activity_events USING gin (source_references jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_activity_file_pending ON activity_events (file_retry_at, sequence) WHERE kind = 'VALIDATION_PASSED'"
    )


def downgrade() -> None:
    op.drop_index("ix_activity_file_pending", table_name="activity_events")
    op.drop_index("ix_activity_references", table_name="activity_events")
    op.drop_column("activity_events", "file_attempts")
    op.drop_column("activity_events", "file_retry_at")
    op.drop_column("activity_events", "file_status")
    op.drop_column("activity_events", "source_references")
