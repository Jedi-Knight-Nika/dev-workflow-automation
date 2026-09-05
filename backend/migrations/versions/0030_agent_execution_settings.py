"""add per-node agent execution settings

Revision ID: 0030_agent_execution_settings
Revises: 0029_default_team_tester
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_agent_execution_settings"
down_revision: str | None = "0029_default_team_tester"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("reasoning_effort", sa.String(20), nullable=False, server_default="default"),
        sa.Column("max_output_tokens", sa.Integer()),
        sa.Column("temperature", sa.Numeric(4, 2)),
        sa.Column("timeout_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_review_cycles", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("context_depth", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("rag_retrieval_depth", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("fallback_provider", sa.String(50)),
        sa.Column("fallback_model", sa.String(255)),
    )
    for column in columns:
        op.add_column("workflow_nodes", column)


def downgrade() -> None:
    for name in (
        "fallback_model",
        "fallback_provider",
        "rag_retrieval_depth",
        "context_depth",
        "max_review_cycles",
        "max_retries",
        "timeout_minutes",
        "temperature",
        "max_output_tokens",
        "reasoning_effort",
    ):
        op.drop_column("workflow_nodes", name)
