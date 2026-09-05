"""durable visual workflow graph

Revision ID: 0020_workflow_graph
Revises: 0019_agent_knowledge
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_workflow_graph"
down_revision: str | None = "0019_agent_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("position_x", sa.Numeric(12, 3), nullable=False),
        sa.Column("position_y", sa.Numeric(12, 3), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("activation_policy", sa.String(20), nullable=False, server_default="any"),
        sa.Column("batch_window_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), sa.ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), sa.ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False, server_default="success"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "source_node_id", "target_node_id", "outcome", name="uq_workflow_edge_route"),
    )


def downgrade() -> None:
    op.drop_table("workflow_edges")
    op.drop_table("workflow_nodes")
    op.drop_table("workflow_definitions")
