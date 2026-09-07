"""Durable question → specialist job → continuation, using existing jobs/messages."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AIAgent,
    Job,
    JobRole,
    JobState,
    Role,
    Task,
    TaskMessage,
    TaskState,
    Team,
    WorkflowNode,
)
from app.domain.workflows.graph import consultation_targets
from app.infrastructure.persistence.job_operations import (
    enqueue_job,
    record_event,
    release_workspace_lease,
)
from app.infrastructure.persistence.workflow_designer import SqlAlchemyWorkflowDesigner


async def available_consultants(
    session: AsyncSession, task: Task, job: Job
) -> list[dict[str, str]]:
    if task.team_id is None or job.workflow_node_id is None or job.action == "CONSULT_AGENT":
        return []
    graph = await SqlAlchemyWorkflowDesigner(session, task.team_id).get()
    if graph.version != job.team_workflow_version:
        return []
    targets = consultation_targets(graph, str(job.workflow_node_id))
    return [
        {"node_id": node.id, "name": node.label, "role": node.role}
        for node in graph.nodes
        if node.id in targets
    ]


class SqlAlchemyConsultationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def complete(
        self, job_id: uuid.UUID, lease_token: uuid.UUID, result: dict[str, Any]
    ) -> bool:
        try:
            return await self._complete(job_id, lease_token, result)
        except (ValueError, KeyError):
            # Configuration can change after a paid answer was checkpointed. Do
            # not repeatedly replay completion or silently run a different graph.
            async with self._sessions() as session, session.begin():
                job = await session.get(Job, job_id, with_for_update=True)
                if (
                    job is None
                    or job.lease_token != lease_token
                    or job.state not in {JobState.CLAIMED, JobState.RUNNING}
                ):
                    return False
                task = await session.get(Task, job.task_id, with_for_update=True)
                if task is None:
                    return False
                job.state = JobState.WAITING_HUMAN
                job.result = result
                job.lease_expires_at = None
                job.failure_reason = "Consultation could not continue with the current workflow configuration. Review the connections and resume the task."
                await release_workspace_lease(session, job)
                task.state = TaskState.NEEDS_HUMAN
                session.add(
                    TaskMessage(
                        task_id=task.id,
                        job_id=job.id,
                        author_type="SYSTEM",
                        author_name="Orchestrator",
                        kind="UPDATE",
                        body=job.failure_reason,
                        context={"blocking": True},
                    )
                )
                await record_event(
                    session, task.id, "CONSULTATION_BLOCKED", {"job_id": str(job.id)}
                )
                return True

    async def _complete(
        self, job_id: uuid.UUID, lease_token: uuid.UUID, result: dict[str, Any]
    ) -> bool:
        async with self._sessions() as session, session.begin():
            job = await session.get(Job, job_id, with_for_update=True)
            if (
                job is None
                or job.lease_token != lease_token
                or job.state not in {JobState.CLAIMED, JobState.RUNNING}
            ):
                return False
            task = await session.get(Task, job.task_id, with_for_update=True)
            if task is None or task.team_id is None:
                return False
            job.state, job.result = JobState.SUCCEEDED, result
            job.finished_at, job.lease_expires_at = datetime.now(UTC), None
            await release_workspace_lease(session, job)
            data = result.get("data") or {}
            team = await session.get(Team, task.team_id)
            if (
                task.manual_takeover
                or task.archived_at is not None
                or task.state in {TaskState.PAUSED, TaskState.CANCELLED, TaskState.MERGED}
                or team is None
                or not team.enabled
            ):
                job.state = JobState.CANCELLED
                await record_event(
                    session, task.id, "CONSULTATION_CANCELLED", {"job_id": str(job.id)}
                )
                return True
            actor = await session.get(AIAgent, job.agent_id) if job.agent_id else None
            if result.get("result") == "CONSULTATION_REQUESTED":
                allowed = {
                    item["node_id"] for item in await available_consultants(session, task, job)
                }
                target_id = str(data.get("target_node_id", ""))
                question = str(data.get("question", "")).strip()
                depth = int(job.payload.get("consultation_depth", 0))
                if target_id not in allowed or not 1 <= len(question) <= 4000 or depth >= 3:
                    raise ValueError("Consultation is unavailable or its budget is exhausted")
                target = await session.get(WorkflowNode, uuid.UUID(target_id))
                target_agent = (
                    await session.get(AIAgent, target.agent_id)
                    if target and target.agent_id
                    else None
                )
                role = await session.get(Role, target_agent.role_id) if target_agent else None
                if (
                    target is None
                    or target_agent is None
                    or not target_agent.enabled
                    or role is None
                    or not role.enabled
                    or role.archived_at is not None
                ):
                    raise ValueError("Consultation recipient is not active")
                message = TaskMessage(
                    task_id=task.id,
                    job_id=job.id,
                    agent_id=job.agent_id,
                    author_type="AGENT",
                    author_name=actor.name if actor else job.role.value,
                    author_role=job.role.value,
                    kind="QUESTION",
                    body=question,
                    context={
                        "target_node_id": target_id,
                        "recipient": target.label,
                        "status": "PENDING",
                    },
                )
                session.add(message)
                await session.flush()
                await enqueue_job(
                    session,
                    task,
                    JobRole(target.role),
                    "CONSULT_AGENT",
                    workflow_node=target,
                    workflow_version=job.team_workflow_version,
                    preserve_task_state=True,
                    payload={
                        "request_job_id": str(job.id),
                        "question_message_id": message.id,
                        "question": question,
                        "consultation_depth": depth + 1,
                    },
                )
                event = "AGENT_QUESTION_SENT"
            elif result.get("result") == "CONSULTATION_REPLIED" and job.action == "CONSULT_AGENT":
                parent = await session.get(Job, uuid.UUID(str(job.payload["request_job_id"])))
                question_message = await session.get(
                    TaskMessage, int(job.payload["question_message_id"])
                )
                if (
                    parent is None
                    or parent.task_id != task.id
                    or question_message is None
                    or question_message.task_id != task.id
                ):
                    raise ValueError("Consultation parent is unavailable")
                graph = await SqlAlchemyWorkflowDesigner(session, task.team_id).get()
                if graph.version != parent.team_workflow_version:
                    raise ValueError("Workflow changed during consultation; replan before resuming")
                source = await session.get(WorkflowNode, parent.workflow_node_id)
                source_agent = (
                    await session.get(AIAgent, source.agent_id)
                    if source and source.agent_id
                    else None
                )
                if (
                    source is None
                    or not source.enabled
                    or source_agent is None
                    or not source_agent.enabled
                ):
                    raise ValueError("Requesting agent is no longer available")
                answer = str(result.get("summary") or data.get("summary") or "").strip()
                if not answer:
                    raise ValueError("Consultation reply cannot be empty")
                session.add(
                    TaskMessage(
                        task_id=task.id,
                        job_id=job.id,
                        reply_to_id=question_message.id,
                        agent_id=job.agent_id,
                        author_type="AGENT",
                        author_name=actor.name if actor else job.role.value,
                        author_role=job.role.value,
                        kind="REPLY",
                        body=answer[:8000],
                        context={"request_job_id": str(parent.id)},
                    )
                )
                question_message.context = {**question_message.context, "status": "ANSWERED"}
                await enqueue_job(
                    session,
                    task,
                    parent.role,
                    parent.action,
                    workflow_node=source,
                    workflow_version=parent.team_workflow_version,
                    preserve_task_state=True,
                    payload={
                        **parent.payload,
                        "consultation_depth": job.payload["consultation_depth"],
                        "consultation_reply": {
                            "question": question_message.body,
                            "answer": answer[:8000],
                            "source_job_id": str(job.id),
                        },
                    },
                )
                event = "AGENT_QUESTION_ANSWERED"
            else:
                raise ValueError("Unsupported consultation result")
            await record_event(session, task.id, event, {"job_id": str(job.id)})
            return True
