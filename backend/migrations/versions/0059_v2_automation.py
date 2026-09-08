"""Explicit V2 rollout policy and durable native spending reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0059_v2_automation"
down_revision = "0058_v2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_automation_policies",
        sa.Column(
            "team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration", sa.JSON(), nullable=False),
    )
    op.add_column("ai_runs", sa.Column("reserved_cost_usd", sa.Numeric(18, 8), nullable=True))
    op.create_table(
        "local_model_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_local_model_runs_task_id", "local_model_runs", ["task_id"])
    op.create_table(
        "external_status_syncs",
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("lifecycle_version", sa.Integer(), nullable=False),
        sa.Column("semantic_status", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(255)),
    )
    op.create_index(
        "ix_external_status_due", "external_status_syncs", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM external_status_syncs)")):
        raise RuntimeError("Preserve tracker delivery evidence before downgrade")
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM local_model_runs)")):
        raise RuntimeError("Preserve local inference evidence before downgrade")
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM team_automation_policies)")):
        raise RuntimeError(
            "Preserve configured V2 policies; export and approve retention before downgrade"
        )
    if connection.scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM ai_runs WHERE reserved_cost_usd IS NOT NULL)")
    ):
        raise RuntimeError("Preserve native spending evidence before downgrade")
    op.drop_column("ai_runs", "reserved_cost_usd")
    op.drop_table("team_automation_policies")
    op.drop_table("local_model_runs")
    op.drop_table("external_status_syncs")
