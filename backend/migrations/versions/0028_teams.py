"""add durable teams and task assignments

Revision ID: 0028_teams
Revises: 0027_task_management_fields
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_teams"
down_revision: str | None = "0027_task_management_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_concurrent_tasks", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("repository_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("max_concurrent_tasks BETWEEN 1 AND 32", name="ck_team_concurrency"),
    )
    op.execute(
        sa.text(
            "INSERT INTO teams (id, name, description) VALUES "
            "(CAST(:id AS uuid), 'Default team', 'Migrated existing workflow')"
        ).bindparams(id=DEFAULT_TEAM_ID)
    )
    op.add_column("tasks", sa.Column("team_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_tasks_team", "tasks", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_tasks_team_state", "tasks", ["team_id", "state"])
    op.execute(
        sa.text("UPDATE tasks SET team_id = CAST(:id AS uuid)").bindparams(id=DEFAULT_TEAM_ID)
    )
    op.add_column("workflow_definitions", sa.Column("team_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_workflow_definitions_team",
        "workflow_definitions",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_workflow_definitions_team", "workflow_definitions", ["team_id"])
    op.execute(
        sa.text("UPDATE workflow_definitions SET team_id = CAST(:id AS uuid)").bindparams(
            id=DEFAULT_TEAM_ID
        )
    )
    op.create_table(
        "task_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("queue_position", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_task_assignments_team_queue",
        "task_assignments",
        ["team_id", "status", "queue_position"],
    )
    op.create_index(
        "uq_task_assignments_active",
        "task_assignments",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )
    op.execute(
        sa.text(
            "INSERT INTO task_assignments (id, task_id, team_id, status, queue_position) "
            "SELECT gen_random_uuid(), id, CAST(:team_id AS uuid), "
            "CASE WHEN state IN ('MERGED', 'CANCELLED', 'FAILED') THEN 'COMPLETED' ELSE 'QUEUED' END, "
            "ROW_NUMBER() OVER (ORDER BY priority, created_at) FROM tasks"
        ).bindparams(team_id=DEFAULT_TEAM_ID)
    )
    op.execute(
        """
        CREATE FUNCTION sync_task_assignment_terminal_state() RETURNS trigger AS $$
        BEGIN
          IF NEW.state IN ('MERGED', 'CANCELLED', 'FAILED')
             AND OLD.state IS DISTINCT FROM NEW.state THEN
            UPDATE task_assignments
               SET status = CASE WHEN NEW.state = 'CANCELLED' THEN 'CANCELLED' ELSE 'COMPLETED' END,
                   completed_at = now()
             WHERE task_id = NEW.id AND status IN ('QUEUED', 'RUNNING');
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_task_assignment_terminal_state
        AFTER UPDATE OF state ON tasks
        FOR EACH ROW EXECUTE FUNCTION sync_task_assignment_terminal_state()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_task_assignment_terminal_state ON tasks")
    op.execute("DROP FUNCTION IF EXISTS sync_task_assignment_terminal_state")
    op.drop_table("task_assignments")
    op.drop_constraint("uq_workflow_definitions_team", "workflow_definitions")
    op.drop_constraint("fk_workflow_definitions_team", "workflow_definitions")
    op.drop_column("workflow_definitions", "team_id")
    op.drop_index("ix_tasks_team_state", table_name="tasks")
    op.drop_constraint("fk_tasks_team", "tasks")
    op.drop_column("tasks", "team_id")
    op.drop_table("teams")
