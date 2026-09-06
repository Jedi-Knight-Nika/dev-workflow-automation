"""add singleton account settings

Revision ID: 0041_account_settings
Revises: 0040_terminal_runtime_ownership
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_account_settings"
down_revision: str | None = "0040_terminal_runtime_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_settings",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("date_format", sa.String(30), nullable=False),
        sa.Column("time_format", sa.String(10), nullable=False),
        sa.Column("default_landing_page", sa.String(50), nullable=False),
        sa.Column("default_task_view", sa.String(30), nullable=False),
        sa.Column("appearance", sa.String(20), nullable=False),
        sa.Column("compact_dashboard", sa.Boolean(), nullable=False),
        sa.Column("default_provider_id", sa.String(50)),
        sa.Column("default_model", sa.String(255)),
        sa.Column("default_reasoning_level", sa.String(20), nullable=False),
        sa.Column("default_max_output_tokens", sa.Integer()),
        sa.Column("provider_failure_behavior", sa.String(40), nullable=False),
        sa.Column("structured_output_retry_limit", sa.Integer(), nullable=False),
        sa.Column("default_execution_mode", sa.String(30), nullable=False),
        sa.Column("default_worker_runtime", sa.String(30), nullable=False),
        sa.Column("max_concurrent_workers", sa.Integer(), nullable=False),
        sa.Column("default_job_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("default_merge_policy", sa.String(30), nullable=False),
        sa.Column("default_unknown_network_policy", sa.String(30), nullable=False),
        sa.Column("default_dependency_install_policy", sa.String(30), nullable=False),
        sa.Column("default_push_task_branch_policy", sa.String(30), nullable=False),
        sa.Column("auto_index_repositories", sa.Boolean(), nullable=False),
        sa.Column("incremental_index_after_merge", sa.Boolean(), nullable=False),
        sa.Column("index_source_code", sa.Boolean(), nullable=False),
        sa.Column("index_tests", sa.Boolean(), nullable=False),
        sa.Column("index_documentation", sa.Boolean(), nullable=False),
        sa.Column("ignore_generated_files", sa.Boolean(), nullable=False),
        sa.Column("context_strategy", sa.String(20), nullable=False),
        sa.Column("completed_workspace_retention_days", sa.Integer(), nullable=False),
        sa.Column("failed_workspace_retention_days", sa.Integer(), nullable=False),
        sa.Column("worker_log_retention_days", sa.Integer(), nullable=False),
        sa.Column("audit_event_retention_days", sa.Integer(), nullable=False),
        sa.Column("monthly_cost_warning", sa.Numeric(14, 2)),
        sa.Column("monthly_cost_hard_stop", sa.Numeric(14, 2)),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "settings_audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("old_values", sa.JSON(), nullable=False),
        sa.Column("new_values", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings_audit_events")
    op.drop_table("account_settings")
