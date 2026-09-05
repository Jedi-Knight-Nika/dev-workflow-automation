"""add workflow node model configuration and validation

Revision ID: 0025_workflow_node_models
Revises: 0024_system_agent_configs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_workflow_node_models"
down_revision: str | None = "0024_system_agent_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_nodes",
        sa.Column("provider", sa.String(50), nullable=False, server_default="openai"),
    )
    op.add_column(
        "workflow_nodes", sa.Column("model", sa.String(255), nullable=False, server_default="")
    )
    op.add_column(
        "workflow_nodes", sa.Column("system_prompt", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "workflow_nodes",
        sa.Column(
            "model_validation_status",
            sa.String(30),
            nullable=False,
            server_default="NOT_CONFIGURED",
        ),
    )
    op.add_column("workflow_nodes", sa.Column("model_validation_message", sa.Text()))
    op.add_column("workflow_nodes", sa.Column("model_validated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for column in (
        "model_validated_at",
        "model_validation_message",
        "model_validation_status",
        "system_prompt",
        "model",
        "provider",
    ):
        op.drop_column("workflow_nodes", column)
