"""Add independent observability and forecast history; preserve all task records."""

import sqlalchemy as sa
from alembic import op

revision = "0002_observability_analytics"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.create_table(
        "runner_resource_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("runner_run_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("container_id", sa.String(64), nullable=False, unique=True),
        sa.Column("container_name", sa.String(255), nullable=False),
        sa.Column("service_kind", sa.String(24), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column(
            "agent_profile_id",
            sa.Uuid(),
            sa.ForeignKey("team_agent_profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("role", sa.String(24)),
        sa.Column("phase", sa.String(24)),
        sa.Column("host_id", sa.String(80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("oom_killed", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_resource_task_started", "runner_resource_bindings", ["task_id", "started_at"]
    )
    op.create_table(
        "runner_resource_summaries",
        sa.Column(
            "runner_run_id",
            sa.Uuid(),
            sa.ForeignKey("runner_resource_bindings.runner_run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sample_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_coverage_ratio", sa.Float()),
        sa.Column("metrics_complete", sa.Boolean(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "infrastructure_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("host_id", sa.String(80), nullable=False),
        sa.Column("container_id", sa.String(64), nullable=False),
        sa.Column("service_name", sa.String(80), nullable=False),
        sa.Column("runner_run_id", sa.Uuid()),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("oom_killed", sa.Boolean()),
    )
    op.create_index("ix_infrastructure_occurred", "infrastructure_events", ["occurred_at"])
    op.create_table(
        "service_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dedup_key", sa.String(180), nullable=False, unique=True),
        sa.Column("service_key", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("summary", sa.String(255), nullable=False),
    )
    op.create_index("ix_incident_opened", "service_incidents", ["opened_at"])
    op.create_table(
        "task_forecasts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("forecast_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_kind", sa.String(40), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("estimates", sa.JSON(), nullable=False),
        sa.Column("actuals", sa.JSON()),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_id", "forecast_version", name="uq_task_forecast_version"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Rollback the application with the observability release disabled; retain additive history tables"
    )
