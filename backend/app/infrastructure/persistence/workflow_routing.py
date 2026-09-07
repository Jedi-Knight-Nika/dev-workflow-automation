import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

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
from app.domain.workflows import (
    WorkflowEdgeData,
    WorkflowGraphData,
    WorkflowNodeData,
    WorkflowRouteNotFound,
)
from app.domain.workflows.routing import resolve_handoff, route_outcomes
from app.infrastructure.persistence.job_operations import enqueue_job, record_event

EXECUTABLE_AGENT_ROLES = frozenset(
    {JobRole.DELIVERER, JobRole.THINKER, JobRole.EXECUTOR, JobRole.TESTER, JobRole.REVIEWER}
)
DEFAULT_JOB_TYPES = {
    JobRole.DELIVERER: "INTERPRET_TASK",
    JobRole.THINKER: "CREATE_PLAN",
    JobRole.EXECUTOR: "IMPLEMENT_PLAN",
    JobRole.TESTER: "RUN_VALIDATION",
    JobRole.REVIEWER: "REVIEW_CHANGES",
}


@dataclass(frozen=True, slots=True)
class ConfiguredRouteResult:
    publish: bool = False
    stopped_for_no_progress: bool = False


def _stable_progress_evidence(value: object) -> object:
    """Remove handoff metadata that changes per Job but does not prove engineering progress."""
    ignored = {"job_id", "task_id", "summary", "reason", "protocol_version"}
    if isinstance(value, dict):
        return {
            key: _stable_progress_evidence(item)
            for key, item in sorted(value.items())
            if key not in ignored
        }
    if isinstance(value, list):
        return [_stable_progress_evidence(item) for item in value]
    return value


async def _stop_repeated_no_progress(
    session: AsyncSession,
    task: Task,
    outcome: str,
    payload: dict[str, object],
) -> bool:
    if outcome not in {
        "TEST_FAILED",
        "FAIL_ACTIONABLE",
        "FAIL_ARCHITECTURAL",
        "PLAN_MISMATCH",
        "NEEDS_REPLAN",
    }:
        task.no_progress_count = 0
        return False
    fingerprint = {
        "repository_sha": task.current_revision,
        "result_type": outcome,
        "evidence_hash": hashlib.sha256(
            json.dumps(_stable_progress_evidence(payload), sort_keys=True, default=str).encode()
        ).hexdigest(),
    }
    if task.progress_fingerprint == fingerprint:
        task.no_progress_count += 1
    else:
        task.progress_fingerprint = fingerprint
        task.no_progress_count = 0
    if task.no_progress_count < 2:
        return False
    task.state = TaskState.NEEDS_HUMAN
    await record_event(
        session,
        task.id,
        "NO_PROGRESS_DETECTED",
        {
            "result": outcome,
            "repetitions": task.no_progress_count + 1,
            "fingerprint": fingerprint,
        },
    )
    return True


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
    intake = payload.get("intake")
    if isinstance(intake, dict) and (
        intake.get("actionability") in {"NEEDS_HUMAN", "INFORMATIONAL"}
        or intake.get("external_delivery_actions")
    ):
        # Interpretation success does not authorize a new engineering handoff.
        return None
    if await _stop_repeated_no_progress(session, task, outcome, payload):
        return ConfiguredRouteResult(stopped_for_no_progress=True)
    job = await session.get(Job, completed_job_id)
    if job is None or job.workflow_node_id is None or job.team_workflow_version is None:
        return None
    definition = await session.get(WorkflowDefinition, task.workflow_id)
    if definition is None or definition.version != job.team_workflow_version:
        return None
    candidate_edges = tuple(
        (
            await session.scalars(
                select(WorkflowEdge).where(
                    WorkflowEdge.workflow_id == definition.id,
                    WorkflowEdge.outcome.in_(route_outcomes(outcome)),
                )
            )
        ).all()
    )
    edge_records = {str(edge.id): edge for edge in candidate_edges}
    node_records = {
        str(node.id): node
        for node in await session.scalars(
            select(WorkflowNode)
            .where(WorkflowNode.workflow_id == definition.id)
            .options(
                load_only(
                    WorkflowNode.id,
                    WorkflowNode.agent_id,
                    WorkflowNode.role,
                    WorkflowNode.label,
                    WorkflowNode.enabled,
                    WorkflowNode.node_type,
                    WorkflowNode.system_node_type,
                )
            )
        )
    }
    edge_data = tuple(
        WorkflowEdgeData(
            id=str(edge.id),
            source_node_id=str(edge.source_node_id),
            target_node_id=str(edge.target_node_id),
            outcome=edge.outcome,
            configuration=edge.configuration,
        )
        for edge in candidate_edges
    )
    try:
        graph = WorkflowGraphData(
            definition.version,
            tuple(
                WorkflowNodeData(
                    id=str(node.id),
                    role=node.role,
                    label=node.label,
                    position_x=0,
                    position_y=0,
                    enabled=node.enabled,
                )
                for node in node_records.values()
            ),
            edge_data,
        )
        handoff = resolve_handoff(graph, str(job.workflow_node_id), outcome)
    except WorkflowRouteNotFound:
        return None
    edge = edge_records[handoff[-1].edge.id]
    target = node_records[handoff[-1].target.id]

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
    elif (
        target.role == JobRole.DELIVERER.value
        and job.role in {JobRole.REVIEWER, JobRole.TESTER}
        and outcome in {"PASS", "REVIEW_PASS", "TEST_PASS"}
    ):
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

    for decision in handoff:
        route_edge = edge_records[decision.edge.id]
        session.add(
            WorkflowTransition(
                task_id=task.id,
                job_id=job.id,
                workflow_id=definition.id,
                workflow_version=job.team_workflow_version,
                from_node_id=uuid.UUID(decision.source.id),
                result_type=outcome,
                matched_edge_id=route_edge.id,
                to_node_id=uuid.UUID(decision.target.id),
                new_job_type=(
                    (
                        route_edge.job_type
                        or (
                            DEFAULT_JOB_TYPES.get(JobRole(target.role))
                            if target.role in {role.value for role in EXECUTABLE_AGENT_ROLES}
                            else None
                        )
                    )
                    if decision is handoff[-1]
                    else None
                ),
                internal_state=route_edge.internal_task_state,
                external_status_key=route_edge.external_status_key,
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
            "handoff_edges": [decision.edge.id for decision in handoff],
        },
    )
    task.current_workflow_node_id = target.id
    return ConfiguredRouteResult(publish)
