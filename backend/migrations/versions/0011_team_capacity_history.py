"""Record capacity policy changes without backdating existing Team configuration."""

from alembic import op

revision = "0011_team_capacity_history"
down_revision = "0010_activity_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE team_capacity_changes (
        id BIGSERIAL PRIMARY KEY,
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        capacity INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT ck_team_capacity_value CHECK (capacity BETWEEN 1 AND 32)
    )""")
    op.execute(
        "CREATE INDEX ix_team_capacity_time ON team_capacity_changes (team_id, created_at, id)"
    )
    op.execute(
        "INSERT INTO team_capacity_changes (team_id, capacity, created_at) SELECT id, max_concurrent_tasks, CURRENT_TIMESTAMP FROM teams"
    )


def downgrade() -> None:
    op.drop_table("team_capacity_changes")
