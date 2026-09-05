"""separate reusable roles from concrete team agents

Revision ID: 0031_roles_and_agents
Revises: 0030_agent_execution_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_roles_and_agents"
down_revision: str | None = "0030_agent_execution_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("system_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_results", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("knowledge_collection_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("default_provider", sa.String(50)),
        sa.Column("default_model", sa.String(255)),
        sa.Column(
            "default_reasoning_effort", sa.String(20), nullable=False, server_default="default"
        ),
        sa.Column("default_timeout_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("default_max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "ai_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(50)),
        sa.Column("model", sa.String(255)),
        sa.Column("custom_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("permission_overrides", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("knowledge_collection_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("team_id", "name", name="uq_ai_agent_team_name"),
    )
    op.add_column("workflow_nodes", sa.Column("agent_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_workflow_nodes_agent",
        "workflow_nodes",
        "ai_agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("worker_runs", sa.Column("agent_id", postgresql.UUID(as_uuid=True)))
    op.add_column("worker_runs", sa.Column("role_id", postgresql.UUID(as_uuid=True)))
    op.add_column("worker_runs", sa.Column("role_version", sa.Integer()))
    op.add_column(
        "worker_runs",
        sa.Column("effective_permissions", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "worker_runs",
        sa.Column("effective_knowledge_scope", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_foreign_key(
        "fk_worker_runs_agent",
        "worker_runs",
        "ai_agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_worker_runs_role", "worker_runs", "roles", ["role_id"], ["id"], ondelete="SET NULL"
    )
    op.execute("""
    INSERT INTO roles (id,name,category,description,system_instructions,capabilities,permissions,allowed_results,built_in)
    VALUES
    ('31000000-0000-0000-0000-000000000001','Orchestrator','COORDINATION','Coordinates deterministic team execution.','Coordinate jobs without bypassing platform policy.','[]','["READ_TASKS"]','["ROUTED","NEEDS_HUMAN"]',true),
    ('31000000-0000-0000-0000-000000000002','Intake','INTAKE','Classifies incoming work.','Normalize and classify the supplied event.','["CAN_CLASSIFY_EXTERNAL_EVENT"]','["READ_TASKS","READ_PR","READ_RAG"]','["EVENT_INTERPRETED","NEEDS_HUMAN","BLOCKED"]',true),
    ('31000000-0000-0000-0000-000000000003','Thinker','PLANNING','Plans and replans implementation work.','Produce concrete plans and escalate missing context.','["CAN_PLAN","CAN_REPLAN"]','["READ_REPOSITORY","READ_DIFF","READ_RAG","READ_TASKS","READ_PR"]','["PLAN_READY","REPLAN_READY","NEEDS_CONTEXT","NEEDS_HUMAN","BLOCKED"]',true),
    ('31000000-0000-0000-0000-000000000004','Executor','EXECUTION','Implements approved plans.','Implement only the approved task plan.','["CAN_IMPLEMENT","CAN_RUN_VALIDATION"]','["READ_REPOSITORY","WRITE_REPOSITORY","RUN_COMMANDS","RUN_TESTS","CREATE_COMMIT","READ_RAG"]','["IMPLEMENTED","TEST_FAILED","PLAN_MISMATCH","NEEDS_REPLAN","BLOCKED","NEEDS_HUMAN"]',true),
    ('31000000-0000-0000-0000-000000000005','Reviewer','REVIEW','Reviews changes independently.','Review correctness, regressions, business rules and tests.','["CAN_REVIEW","CAN_PRODUCE_FINDINGS","CAN_RUN_VALIDATION"]','["READ_REPOSITORY","READ_DIFF","RUN_TESTS","READ_RAG","READ_PR","READ_CI"]','["PASS","FAIL_ACTIONABLE","FAIL_ARCHITECTURAL","UNCERTAIN","NEEDS_HUMAN","BLOCKED"]',true),
    ('31000000-0000-0000-0000-000000000006','Tester','REVIEW','Verifies implementation evidence.','Verify tests and report only evidenced results.','["CAN_REVIEW","CAN_RUN_VALIDATION"]','["READ_REPOSITORY","READ_DIFF","RUN_TESTS","READ_RAG","READ_CI"]','["PASS","FAIL_ACTIONABLE","UNCERTAIN","NEEDS_HUMAN","BLOCKED"]',true),
    ('31000000-0000-0000-0000-000000000007','Deliverer','COORDINATION','Publishes approved work through deterministic integrations.','Return control to deterministic delivery policy.','[]','["READ_PR","READ_CI"]','["DELIVERED","BLOCKED"]',true);

    INSERT INTO ai_agents (id,team_id,role_id,name,provider,model,custom_instructions,enabled)
    SELECT gen_random_uuid(), wd.team_id,
      CASE wn.role WHEN 'ORCHESTRATOR' THEN '31000000-0000-0000-0000-000000000001'::uuid
        WHEN 'INTAKE' THEN '31000000-0000-0000-0000-000000000002'::uuid
        WHEN 'THINKER' THEN '31000000-0000-0000-0000-000000000003'::uuid
        WHEN 'EXECUTOR' THEN '31000000-0000-0000-0000-000000000004'::uuid
        WHEN 'REVIEWER' THEN '31000000-0000-0000-0000-000000000005'::uuid
        WHEN 'TESTER' THEN '31000000-0000-0000-0000-000000000006'::uuid
        ELSE '31000000-0000-0000-0000-000000000007'::uuid END,
      wn.label, NULLIF(wn.provider,''), NULLIF(wn.model,''), wn.system_prompt, wn.enabled
    FROM workflow_nodes wn JOIN workflow_definitions wd ON wd.id=wn.workflow_id WHERE wd.team_id IS NOT NULL;
    UPDATE workflow_nodes wn SET agent_id=a.id FROM workflow_definitions wd, ai_agents a
      WHERE wd.id=wn.workflow_id AND a.team_id=wd.team_id AND a.name=wn.label;
    """)


def downgrade() -> None:
    op.drop_constraint("fk_worker_runs_role", "worker_runs", type_="foreignkey")
    op.drop_constraint("fk_worker_runs_agent", "worker_runs", type_="foreignkey")
    for name in (
        "effective_knowledge_scope",
        "effective_permissions",
        "role_version",
        "role_id",
        "agent_id",
    ):
        op.drop_column("worker_runs", name)
    op.drop_constraint("fk_workflow_nodes_agent", "workflow_nodes", type_="foreignkey")
    op.drop_column("workflow_nodes", "agent_id")
    op.drop_table("ai_agents")
    op.drop_table("roles")
