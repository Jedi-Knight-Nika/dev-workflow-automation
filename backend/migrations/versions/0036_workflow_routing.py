"""make team workflow routing executable and auditable

Revision ID: 0036_workflow_routing
Revises: 0035_task_memory
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_workflow_routing"
down_revision: str | None = "0035_task_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_definitions",
        sa.Column("name", sa.String(120), nullable=False, server_default="Team workflow"),
    )
    op.add_column(
        "workflow_definitions",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("workflow_definitions", sa.Column("entry_node_id", postgresql.UUID(as_uuid=True)))
    op.add_column(
        "workflow_nodes",
        sa.Column("node_type", sa.String(30), nullable=False, server_default="AGENT"),
    )
    op.add_column("workflow_nodes", sa.Column("system_node_type", sa.String(30)))
    op.add_column("workflow_edges", sa.Column("job_type", sa.String(100)))
    op.add_column("workflow_edges", sa.Column("internal_task_state", sa.String(50)))
    op.add_column("workflow_edges", sa.Column("external_status_key", sa.String(100)))
    op.add_column("workflow_edges", sa.Column("priority_override", sa.Integer()))
    op.add_column(
        "workflow_edges",
        sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("tasks", sa.Column("workflow_id", postgresql.UUID(as_uuid=True)))
    op.add_column("tasks", sa.Column("workflow_version", sa.Integer()))
    op.add_column("tasks", sa.Column("current_workflow_node_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_tasks_workflow",
        "tasks",
        "workflow_definitions",
        ["workflow_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("jobs", sa.Column("workflow_node_id", postgresql.UUID(as_uuid=True)))
    op.add_column("jobs", sa.Column("agent_id", postgresql.UUID(as_uuid=True)))
    op.add_column("jobs", sa.Column("team_workflow_version", sa.Integer()))
    op.create_foreign_key(
        "fk_jobs_agent", "jobs", "ai_agents", ["agent_id"], ["id"], ondelete="SET NULL"
    )
    op.create_table(
        "workflow_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("from_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_type", sa.String(80), nullable=False),
        sa.Column("matched_edge_id", postgresql.UUID(as_uuid=True)),
        sa.Column("to_node_id", postgresql.UUID(as_uuid=True)),
        sa.Column("new_job_type", sa.String(100)),
        sa.Column("internal_state", sa.String(50)),
        sa.Column("external_status_key", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_workflow_transitions_task_created",
        "workflow_transitions",
        ["task_id", "created_at"],
    )
    op.execute("""
        UPDATE workflow_definitions wd
        SET entry_node_id = wn.id
        FROM workflow_nodes wn
        WHERE wn.workflow_id = wd.id AND wn.role = 'ORCHESTRATOR'
    """)
    op.execute("""
        UPDATE roles SET
          category = 'VALIDATION',
          capabilities = '["CAN_RUN_VALIDATION","CAN_PRODUCE_FINDINGS"]',
          permissions = '["READ_REPOSITORY","READ_DIFF","READ_TASK","RUN_COMMANDS","RUN_TESTS","RUN_BUILD","RUN_LINTER","READ_RAG"]',
          allowed_results = '["TEST_PASS","TEST_FAILED","TEST_ENVIRONMENT_FAILURE","TEST_INCOMPLETE","NEEDS_HUMAN","BLOCKED"]',
          version = version + 1
        WHERE built_in AND name = 'Tester';

        UPDATE roles SET
          category = 'REVIEW',
          allowed_results = '["REVIEW_PASS","FAIL_ACTIONABLE","FAIL_ARCHITECTURAL","NEEDS_HUMAN","BLOCKED"]',
          version = version + 1
        WHERE built_in AND name = 'Reviewer';

        UPDATE roles SET
          category = 'DELIVERY',
          capabilities = '["CAN_PREPARE_DELIVERY","CAN_CREATE_PR_METADATA"]',
          permissions = '["READ_REPOSITORY","READ_DIFF","READ_PR","READ_CI","PUSH_TASK_BRANCH","CREATE_PR","UPDATE_PR"]',
          allowed_results = '["DELIVERY_READY","DELIVERY_FAILED","DELIVERY_BLOCKED","NEEDS_HUMAN"]',
          version = version + 1
        WHERE built_in AND name = 'Deliverer';
    """)


def downgrade() -> None:
    op.drop_index("ix_workflow_transitions_task_created", table_name="workflow_transitions")
    op.drop_table("workflow_transitions")
    op.drop_constraint("fk_jobs_agent", "jobs", type_="foreignkey")
    for column in ("team_workflow_version", "agent_id", "workflow_node_id"):
        op.drop_column("jobs", column)
    op.drop_constraint("fk_tasks_workflow", "tasks", type_="foreignkey")
    for column in ("current_workflow_node_id", "workflow_version", "workflow_id"):
        op.drop_column("tasks", column)
    for column in (
        "configuration",
        "priority_override",
        "external_status_key",
        "internal_task_state",
        "job_type",
    ):
        op.drop_column("workflow_edges", column)
    for column in ("system_node_type", "node_type"):
        op.drop_column("workflow_nodes", column)
    for column in ("entry_node_id", "is_active", "name"):
        op.drop_column("workflow_definitions", column)
