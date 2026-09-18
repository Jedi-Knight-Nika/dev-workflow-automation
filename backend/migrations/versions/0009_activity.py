"""Independent activity read model; no existing business tables are modified."""

from alembic import op

revision = "0009_activity"
down_revision = "0008_coordinator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE activity_events (
            sequence BIGSERIAL NOT NULL,
            id UUID NOT NULL,
            task_id UUID NOT NULL,
            kind VARCHAR(100) NOT NULL,
            detail_level INTEGER NOT NULL,
            actor_type VARCHAR(20) NOT NULL,
            actor VARCHAR(120) NOT NULL,
            occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
            source_type VARCHAR(30) NOT NULL,
            source_id VARCHAR(200) NOT NULL,
            correlation_id UUID,
            payload JSONB NOT NULL,
            projector_version INTEGER NOT NULL,
            file_checked_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (sequence),
            CONSTRAINT uq_activity_source UNIQUE (source_type, source_id),
            UNIQUE (id),
            FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_activity_task_time ON activity_events (task_id, occurred_at, sequence)"
    )
    op.execute("CREATE INDEX ix_activity_time ON activity_events (occurred_at, sequence)")
    op.execute(
        """
        CREATE TABLE activity_file_changes (
            id UUID NOT NULL,
            event_sequence BIGINT NOT NULL,
            repository_id UUID NOT NULL,
            operation VARCHAR(1) NOT NULL,
            path VARCHAR(1000) NOT NULL,
            previous_path VARCHAR(1000),
            lines_added INTEGER,
            lines_deleted INTEGER,
            PRIMARY KEY (id),
            FOREIGN KEY(event_sequence) REFERENCES activity_events (sequence) ON DELETE CASCADE,
            FOREIGN KEY(repository_id) REFERENCES repositories (id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_activity_files_event ON activity_file_changes (event_sequence)")
    op.execute(
        """
        CREATE TABLE activity_projection_state (
            id INTEGER NOT NULL,
            last_success_at TIMESTAMP WITH TIME ZONE,
            caught_up BOOLEAN NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )


def downgrade() -> None:
    op.drop_table("activity_projection_state")
    op.drop_table("activity_file_changes")
    op.drop_table("activity_events")
