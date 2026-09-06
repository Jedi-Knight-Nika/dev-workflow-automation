"""add normalized role runtime profiles and agent overrides

Revision ID: 0043_role_runtime_profiles
Revises: 0042_adaptive_orchestration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_role_runtime_profiles"
down_revision: str | None = "0042_adaptive_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("roles", sa.Column("runtime_profile", sa.JSON(), nullable=True))
    op.add_column("roles", sa.Column("override_policy", sa.JSON(), nullable=True))
    op.execute(
        """
        UPDATE roles SET runtime_profile = json_build_object(
            'reasoning_default', CASE
                WHEN upper(default_reasoning_effort) = 'DEFAULT' THEN 'PROVIDER_DEFAULT'
                ELSE upper(default_reasoning_effort)
            END,
            'reasoning_min', 'PROVIDER_DEFAULT',
            'reasoning_max', 'MAX',
            'dynamic_reasoning_allowed', true,
            'max_output_tokens', NULL,
            'temperature', NULL,
            'context_strategy', CASE category
                WHEN 'PLANNING' THEN 'DEEP'
                WHEN 'DELIVERY' THEN 'MINIMAL'
                ELSE 'BALANCED'
            END,
            'max_tool_calls', CASE category
                WHEN 'EXECUTION' THEN 80
                WHEN 'DELIVERY' THEN 15
                WHEN 'VALIDATION' THEN 30
                ELSE 40
            END,
            'job_timeout_seconds', default_timeout_minutes * 60,
            'max_job_attempts', default_max_retries,
            'max_model_turns', 3,
            'structured_output_mode', 'REQUIRED'
        ), override_policy = json_build_object(
            'provider', 'ALLOW', 'model', 'ALLOW',
            'reasoning_level', 'ALLOW_WITHIN_RANGE',
            'max_output_tokens', 'ALLOW',
            'temperature', 'ALLOW_IF_SUPPORTED',
            'context_strategy', 'ALLOW',
            'max_tool_calls', 'ALLOW_WITHIN_RANGE',
            'job_timeout_seconds', 'ALLOW_WITHIN_RANGE',
            'permissions', 'REDUCE_ONLY',
            'system_instructions', 'ADDITIVE_ONLY',
            'allowed_results', 'LOCKED'
        )
        """
    )
    op.alter_column("roles", "runtime_profile", nullable=False)
    op.alter_column("roles", "override_policy", nullable=False)
    op.add_column(
        "ai_agents", sa.Column("runtime_overrides", sa.JSON(), server_default="{}", nullable=False)
    )
    op.add_column(
        "ai_agents", sa.Column("config_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "worker_runs",
        sa.Column("effective_runtime_config", sa.JSON(), server_default="{}", nullable=False),
    )
    op.add_column(
        "worker_runs", sa.Column("effective_runtime_config_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "worker_runs", sa.Column("model_capability_version", sa.String(30), nullable=True)
    )
    op.add_column("worker_runs", sa.Column("agent_config_version", sa.Integer(), nullable=True))
    op.add_column("worker_runs", sa.Column("strategy_version", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("worker_runs", "strategy_version")
    op.drop_column("worker_runs", "agent_config_version")
    op.drop_column("worker_runs", "model_capability_version")
    op.drop_column("worker_runs", "effective_runtime_config_hash")
    op.drop_column("worker_runs", "effective_runtime_config")
    op.drop_column("ai_agents", "config_version")
    op.drop_column("ai_agents", "runtime_overrides")
    op.drop_column("roles", "override_policy")
    op.drop_column("roles", "runtime_profile")
