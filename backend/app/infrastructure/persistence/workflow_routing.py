import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Job,
    JobRole,
    Task,
    TaskState,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowTransition,
)
from app.infrastructure.persistence.job_operations import enqueue_job, record_event

EXECUTABLE_AGENT_ROLES = frozenset(
    {JobRole.INTAKE, JobRole.THINKER, JobRole.EXECUTOR, JobRole.TESTER, JobRole.REVIEWER}
)
DEFAULT_JOB_TYPES = {
    JobRole.INTAKE: "INTERPRET_TASK",
    JobRole.THINKER: "CREATE_PLAN",
    JobRole.EXECUTOR: "IMPLEMENT_PLAN",
    JobRole.TESTER: "RUN_VALIDATION",
    JobRole.REVIEWER: "REVIEW_CHANGES",
}


@dataclass(frozen=True, slots=True)
class ConfiguredRouteResult:
    publish: bool = False


async def route_completed_job(
    session: AsyncSession,
    task: Task,
    completed_job_id: uuid.UUID,
    outcome: str | None,
    payload: dict[str, object],
) -> ConfiguredRouteResult | None:
    """Apply a current, pinned graph edge or return None for legacy compatibility routing."""
    if not outcome or task.workflow_id is None:
        return None
    job = await session.get(Job, completed_job_id)
    if job is None or job.workflow_node_id is None or job.team_workflow_version is None:
        return None
    definition = await session.get(WorkflowDefinition, task.workflow_id)
    if definition is None or definition.version != job.team_workflow_version:
        return None
    edge = await session.scalar(
        select(WorkflowEdge).where(
            WorkflowEdge.workflow_id == definition.id,
            WorkflowEdge.source_node_id == job.workflow_node_id,
            WorkflowEdge.outcome == outcome,
        )
    )
    if edge is None:
        edge = await session.scalar(
            select(WorkflowEdge).where(
                WorkflowEdge.workflow_id == definition.id,
                WorkflowEdge.source_node_id == job.workflow_node_id,
                WorkflowEdge.outcome == "always",
            )
        )
    if edge is None:
        return None
    target = await session.get(WorkflowNode, edge.target_node_id)
    if target is None or not target.enabled:
        return None

    publish = False
    if target.node_type != "AGENT":
        if target.system_node_type in {"HUMAN_ATTENTION", "TASK_FAILED"}:
            task.state = TaskState.NEEDS_HUMAN
        elif target.system_node_type in {"WAIT_EXTERNAL", "MERGE_GATE"}:
            task.state = TaskState.WAITING_GITHUB
        elif target.system_node_type == "TASK_COMPLETE":
            task.state = TaskState.READY_TO_MERGE
        else:
            return None
    elif target.role == JobRole.DELIVERER.value:
        if job.role != JobRole.REVIEWER:
            return None
        task.state = TaskState.WAITING_GITHUB
        publish = True
    else:
        try:
            target_role = JobRole(target.role)
        except ValueError:
            return None
        if target_role not in EXECUTABLE_AGENT_ROLES:
            return None
        await enqueue_job(
            session,
            task,
            target_role,
            edge.job_type or DEFAULT_JOB_TYPES[target_role],
            priority=edge.priority_override,
            payload=payload,
            workflow_node=target,
            workflow_version=job.team_workflow_version,
        )
        if edge.internal_task_state:
            try:
                task.state = TaskState(edge.internal_task_state)
            except ValueError:
                task.state = TaskState.NEEDS_HUMAN

    session.add(
        WorkflowTransition(
            task_id=task.id,
            job_id=job.id,
            workflow_id=definition.id,
            workflow_version=job.team_workflow_version,
            from_node_id=job.workflow_node_id,
            result_type=outcome,
            matched_edge_id=edge.id,
            to_node_id=target.id,
            new_job_type=(
                edge.job_type
                or (
                    DEFAULT_JOB_TYPES.get(JobRole(target.role))
                    if target.role in {role.value for role in EXECUTABLE_AGENT_ROLES}
                    else None
                )
            ),
            internal_state=edge.internal_task_state,
            external_status_key=edge.external_status_key,
        )
    )
    await record_event(
        session,
        task.id,
        "WORKFLOW_ROUTE_APPLIED",
        {
            "job_id": str(job.id),
            "result": outcome,
            "edge_id": str(edge.id),
            "target_node_id": str(target.id),
            "target_role": target.role,
        },
    )
    task.current_workflow_node_id = target.id
    return ConfiguredRouteResult(publish)
