"""Indexed tracker search without duplicated application-side synchronization."""

import sqlalchemy as sa
from alembic import op

revision = "0016_search_indexes"
down_revision = "0015_notification_outbox"
branch_labels = None
depends_on = None

FIELDS = {
    "assignee_name": "raw_payload->'assignee'->>'name'",
    "assignee_email": "raw_payload->'assignee'->>'email'",
    "team_name": "raw_payload->'team'->>'name'",
    "project_name": "raw_payload->'project'->>'name'",
    "state_name": "raw_payload->'state'->>'name'",
    "labels_text": "lower((raw_payload->'labels')::text)",
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, expression in FIELDS.items():
        op.add_column(
            "external_task_snapshots", sa.Column(name, sa.Text(), sa.Computed(expression))
        )
        op.create_index(
            f"ix_snapshot_{name}_search",
            "external_task_snapshots",
            [name],
            postgresql_using="gin",
            postgresql_ops={name: "gin_trgm_ops"},
        )
    for name in ("assignee_id", "state_id"):
        op.create_index(f"ix_snapshot_{name}", "external_task_snapshots", [name])
    for name in ("title", "external_key", "project_name"):
        op.create_index(
            f"ix_tasks_{name}_search",
            "tasks",
            [name],
            postgresql_using="gin",
            postgresql_ops={name: "gin_trgm_ops"},
        )
    op.execute(
        "CREATE INDEX ix_tasks_labels_search ON tasks USING gin (lower(labels::text) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_labels_search", table_name="tasks")
    for name in ("title", "external_key", "project_name"):
        op.drop_index(f"ix_tasks_{name}_search", table_name="tasks")
    for name in ("assignee_id", "state_id"):
        op.drop_index(f"ix_snapshot_{name}", table_name="external_task_snapshots")
    for name in FIELDS:
        op.drop_index(f"ix_snapshot_{name}_search", table_name="external_task_snapshots")
        op.drop_column("external_task_snapshots", name)
