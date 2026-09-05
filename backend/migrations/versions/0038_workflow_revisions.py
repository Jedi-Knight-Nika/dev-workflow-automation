"""preserve workflow revisions and finish hot-path indexes

Revision ID: 0038_workflow_revisions
Revises: 0037_query_path_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_workflow_revisions"
down_revision: str | None = "0037_query_path_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_tool_events_team", "tool_execution_events", ["team_id"])
    op.create_table(
        "workflow_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_revision_version"),
    )
    op.create_index("ix_workflow_revisions_workflow", "workflow_revisions", ["workflow_id"])
    op.execute("""
        INSERT INTO agent_configs (role, enabled, provider, model, configuration, updated_at)
        SELECT role, true, 'openai', '', '{}'::json, now()
        FROM unnest(enum_range(NULL::jobrole)) AS role
        ON CONFLICT (role) DO NOTHING
    """)
    # Existing graphs can only be preserved from their current version onward. Snapshot that
    # version during migration so future edits never erase the current baseline.
    op.execute("""
        INSERT INTO workflow_revisions (id, workflow_id, version, graph)
        SELECT gen_random_uuid(), wd.id, wd.version,
               jsonb_build_object(
                   'version', wd.version,
                   'nodes', COALESCE((
                       SELECT jsonb_agg(to_jsonb(wn) ORDER BY wn.id)
                       FROM workflow_nodes wn WHERE wn.workflow_id = wd.id
                   ), '[]'::jsonb),
                   'edges', COALESCE((
                       SELECT jsonb_agg(to_jsonb(we) ORDER BY we.id)
                       FROM workflow_edges we WHERE we.workflow_id = wd.id
                   ), '[]'::jsonb)
               )
        FROM workflow_definitions wd
    """)


def downgrade() -> None:
    op.drop_index("ix_workflow_revisions_workflow", table_name="workflow_revisions")
    op.drop_table("workflow_revisions")
    op.drop_index("ix_tool_events_team", table_name="tool_execution_events")
