from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ExternalTaskSnapshot,
    Integration,
    Job,
    JobRole,
    JobState,
    Task,
    TaskState,
    WebhookDelivery,
    WorkflowNode,
)
from app.domain.webhooks import (
    DeliveryRetryPolicy,
    configured_repository_id,
    issue_labels,
    linear_comment,
    linear_datetime,
    linear_priority,
)
from app.infrastructure.persistence.job_operations import enqueue_job, record_event
from app.infrastructure.persistence.team_routing import assign_routed_team


async def process_linear_delivery(session: AsyncSession, delivery: WebhookDelivery) -> None:
    payload = delivery.payload
    comment = linear_comment(payload)
    if comment:
        comment_identifier, intake_payload = comment
        task = await session.scalar(select(Task).where(Task.external_key == comment_identifier))
        if task is None:
            delivery.status = "IGNORED"
            return
        active = await session.scalar(
            select(func.count(Job.id)).where(
                Job.task_id == task.id,
                Job.role == JobRole.INTAKE,
                Job.state.in_(
                    [JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING, JobState.RETRY_WAIT]
                ),
            )
        )
        if not active:
            intake_payload["previous_state"] = task.state.value
            await enqueue_job(
                session,
                task,
                JobRole.INTAKE,
                "INTERPRET_EXTERNAL_COMMENT",
                payload=intake_payload,
            )
            await record_event(
                session,
                task.id,
                "LINEAR_COMMENT_QUEUED_FOR_INTAKE",
                {key: value for key, value in intake_payload.items() if key != "raw_text"},
                source="linear",
            )
        delivery.status = "PROCESSED"
        return
    if payload.get("type") != "Issue":
        delivery.status = "IGNORED"
        return
    data = payload.get("data") or {}
    identifier = data.get("identifier")
    if not identifier:
        delivery.status = "IGNORED"
        return
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "linear")
    )
    configuration = integration.configuration if integration else {}
    trigger_label = str(configuration.get("trigger_label", "AI Ready"))
    task = await session.scalar(select(Task).where(Task.external_key == str(identifier)))
    if payload.get("action") == "remove" or data.get("archivedAt"):
        if task:
            task.state = TaskState.CANCELLED
            await record_event(session, task.id, "LINEAR_ISSUE_REMOVED", {}, source="linear")
        delivery.status = "PROCESSED"
        return
    intake_nodes = list(
        (
            await session.scalars(
                select(WorkflowNode).where(
                    WorkflowNode.role == "INTAKE",
                    WorkflowNode.enabled.is_(True),
                    WorkflowNode.integration_mode.in_(["webhook", "hybrid"]),
                )
            )
        ).all()
    )
    configured_nodes = [
        node
        for node in intake_nodes
        if integration is not None and str(integration.id) in (node.integration_ids or [])
    ]
    assignee_id = str((data.get("assignee") or {}).get("id") or "")
    state_id = str((data.get("state") or {}).get("id") or "")
    triggered = (
        any(
            (not node.filter_assignee_id or node.filter_assignee_id == assignee_id)
            and (not node.filter_state_ids or state_id in node.filter_state_ids)
            for node in configured_nodes
        )
        if configured_nodes
        else trigger_label in issue_labels(data)
    )
    if task is None and not triggered:
        delivery.status = "IGNORED"
        return
    if task is None:
        task = Task(
            external_key=str(identifier),
            title=str(data.get("title") or identifier),
            description=str(data.get("description") or ""),
            priority=linear_priority(data.get("priority")),
            repository_id=configured_repository_id(configuration),
        )
        session.add(task)
        await session.flush()
        await assign_routed_team(session, task, reason="linear-webhook")
        await record_event(
            session,
            task.id,
            "TASK_CREATED_FROM_LINEAR",
            {"linear_issue_id": data.get("id"), "identifier": identifier},
            source="linear",
        )
        await enqueue_job(
            session,
            task,
            JobRole.INTAKE,
            "INTERPRET_TASK",
            payload={
                "source": "linear",
                "linear_issue_id": data.get("id"),
                "raw": {"title": data.get("title"), "description": data.get("description")},
            },
        )
    else:
        task.title = str(data.get("title") or task.title)
        task.description = str(data.get("description") or task.description)
        task.priority = linear_priority(data.get("priority"))
        await record_event(
            session,
            task.id,
            "TASK_UPDATED_FROM_LINEAR",
            {"action": payload.get("action")},
            source="linear",
        )
    linear_issue_id = str(data.get("id") or "")
    task.due_at = linear_datetime(data.get("dueDate"))
    task.started_at = linear_datetime(data.get("startedAt"))
    task.completed_at = linear_datetime(data.get("completedAt"))
    if linear_issue_id:
        snapshot = await session.scalar(
            select(ExternalTaskSnapshot).where(
                ExternalTaskSnapshot.provider == "linear",
                ExternalTaskSnapshot.external_id == linear_issue_id,
            )
        )
        if snapshot is None:
            snapshot = ExternalTaskSnapshot(
                task_id=task.id,
                provider="linear",
                external_id=linear_issue_id,
                identifier=str(identifier),
            )
            session.add(snapshot)
        snapshot.task_id = task.id
        snapshot.assignee_id = assignee_id or None
        snapshot.state_id = state_id or None
        snapshot.raw_payload = dict(data)
        snapshot.synchronized_at = datetime.now(UTC)
    delivery.status = "PROCESSED"


async def process_next_linear_delivery(session: AsyncSession, max_attempts: int = 5) -> bool:
    retry_policy = DeliveryRetryPolicy(max_attempts)
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(WebhookDelivery.provider == "linear", WebhookDelivery.status == "RECEIVED")
        .order_by(WebhookDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return False
    delivery_id = delivery.id
    try:
        delivery.attempts += 1
        await process_linear_delivery(session, delivery)
        if delivery.status == "RECEIVED":
            delivery.status = "PROCESSED"
        delivery.last_error = None
        delivery.processed_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed = await session.get(WebhookDelivery, delivery_id, with_for_update=True)
        if failed is None:
            raise
        failed.attempts += 1
        failed.last_error = retry_policy.error_message(exc)
        if retry_policy.exhausted(failed.attempts):
            failed.status = "FAILED"
            failed.processed_at = datetime.now(UTC)
        await session.commit()
    return True
