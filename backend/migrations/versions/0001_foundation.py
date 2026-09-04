"""foundation task, job, and event tables"""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    task_state = sa.Enum(
        "NEW",
        "PLANNING",
        "PLAN_READY",
        "QUEUED_FOR_EXECUTION",
        "IMPLEMENTING",
        "LOCAL_VALIDATION",
        "INTERNAL_REVIEW",
        "WAITING_GITHUB",
        "READY_TO_MERGE",
        "NEEDS_HUMAN",
        "PAUSED",
        "CANCELLED",
        "FAILED",
        name="taskstate",
    )
    job_state = sa.Enum(
        "QUEUED",
        "CLAIMED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
        "RETRY_WAIT",
        name="jobstate",
    )
    job_role = sa.Enum("INTAKE", "THINKER", "EXECUTOR", "REVIEWER", name="jobrole")
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("external_key", sa.String(100), nullable=True, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("state", task_state, nullable=False, server_default="NEW"),
        sa.Column("current_revision", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", job_role, nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("state", job_state, nullable=False, server_default="QUEUED"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("worker_id", sa.String(200)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_claim", "jobs", ["state", "priority", "created_at"])
    op.create_table(
        "task_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("external_event_id", sa.String(255)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "external_event_id", name="uq_event_source_external_id"),
    )


def downgrade() -> None:
    op.drop_table("task_events")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("tasks")
    for enum_name in ("jobrole", "jobstate", "taskstate"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
