"""index foreign keys used by scheduler, dashboard, routing, and cascades

Revision ID: 0037_query_path_indexes
Revises: 0036_workflow_routing
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037_query_path_indexes"
down_revision: str | None = "0036_workflow_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_tasks_repository", "tasks", ("repository_id",)),
    ("ix_tasks_workflow", "tasks", ("workflow_id",)),
    ("ix_jobs_task", "jobs", ("task_id",)),
    ("ix_jobs_agent", "jobs", ("agent_id",)),
    ("ix_task_events_task", "task_events", ("task_id",)),
    ("ix_agent_knowledge_chunks_source", "agent_knowledge_chunks", ("source_id",)),
    ("ix_workflow_nodes_workflow", "workflow_nodes", ("workflow_id",)),
    ("ix_workflow_nodes_agent", "workflow_nodes", ("agent_id",)),
    ("ix_external_task_snapshots_task", "external_task_snapshots", ("task_id",)),
    ("ix_workflow_edges_source", "workflow_edges", ("source_node_id",)),
    ("ix_workflow_edges_target", "workflow_edges", ("target_node_id",)),
    ("ix_workflow_transitions_job", "workflow_transitions", ("job_id",)),
    ("ix_workflow_transitions_workflow", "workflow_transitions", ("workflow_id",)),
    ("ix_terminal_sessions_task", "terminal_sessions", ("task_id",)),
    ("ix_worker_runs_job", "worker_runs", ("job_id",)),
    ("ix_worker_runs_agent", "worker_runs", ("agent_id",)),
    ("ix_worker_runs_role", "worker_runs", ("role_id",)),
    ("ix_task_memories_plan_job", "task_memories", ("current_plan_job_id",)),
    ("ix_agent_checkpoints_agent", "agent_checkpoints", ("agent_id",)),
    ("ix_agent_checkpoints_role_id", "agent_checkpoints", ("role_id",)),
    ("ix_job_contexts_plan_job", "job_contexts", ("plan_job_id",)),
    ("ix_ai_agents_role", "ai_agents", ("role_id",)),
    ("ix_task_assignments_task", "task_assignments", ("task_id",)),
    ("ix_approvals_team_state", "approval_requests", ("team_id", "state")),
    ("ix_approvals_task", "approval_requests", ("task_id",)),
    ("ix_approvals_job", "approval_requests", ("job_id",)),
    ("ix_tool_events_job", "tool_execution_events", ("job_id",)),
    ("ix_incidents_team", "incidents", ("team_id",)),
    ("ix_incidents_task", "incidents", ("task_id",)),
    ("ix_incidents_job", "incidents", ("job_id",)),
    ("ix_incidents_integration", "incidents", ("integration_id",)),
    ("ix_notifications_incident", "notifications", ("incident_id",)),
    ("ix_notifications_team", "notifications", ("team_id",)),
    ("ix_notifications_task", "notifications", ("task_id",)),
    ("ix_notifications_job", "notifications", ("job_id",)),
    ("ix_notification_deliveries_notification", "notification_deliveries", ("notification_id",)),
    ("ix_workspace_leases_job", "workspace_leases", ("job_id",)),
    ("ix_review_findings_reviewer_job", "review_findings", ("reviewer_job_id",)),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, list(columns))


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
