"""Explicit prerequisites; existing tasks retain independent scheduling."""

from alembic import op

revision = "0012_task_dependencies"
down_revision = "0011_team_capacity_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE task_dependencies (
        task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        prerequisite_id UUID NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        PRIMARY KEY (task_id, prerequisite_id),
        CONSTRAINT ck_task_dependency_self CHECK (task_id != prerequisite_id)
    )""")
    op.create_index("ix_task_dependencies_prerequisite", "task_dependencies", ["prerequisite_id"])


def downgrade() -> None:
    op.drop_table("task_dependencies")
