import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, Job, JobRole, JobState, Task, TaskState, WebhookDelivery
from app.services.orchestrator import enqueue_job, record_event


def linear_priority(value: object) -> int:
    if not isinstance(value, int):
        return 3
    return {1: 1, 2: 3, 3: 3, 4: 4}.get(value, 3)


def issue_labels(data: dict[str, Any]) -> set[str]:
    labels = data.get("labels") or []
    if isinstance(labels, dict):
        labels = labels.get("nodes") or []
    return {str(item.get("name")) for item in labels if isinstance(item, dict) and item.get("name")}


def configured_repository_id(configuration: dict[str, Any]) -> uuid.UUID | None:
    value = configuration.get("repository_id")
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def linear_comment(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if payload.get("type") != "Comment" or payload.get("action") not in {"create", "update"}:
        return None
    data = payload.get("data") or {}
    issue = data.get("issue") or {}
    identifier = issue.get("identifier") or data.get("issueIdentifier")
    body = str(data.get("body") or "").strip()
    if not identifier or not body:
        return None
    return str(identifier), {
        "source": "linear",
        "event_type": "comment",
        "author": (data.get("user") or {}).get("name"),
        "url": data.get("url"),
        "raw_text": body,
    }


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
    triggered = trigger_label in issue_labels(data)
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
    delivery.status = "PROCESSED"


async def process_next_linear_delivery(session: AsyncSession, max_attempts: int = 5) -> bool:
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
        failed.last_error = str(exc)[:2000]
        if failed.attempts >= max_attempts:
            failed.status = "FAILED"
            failed.processed_at = datetime.now(UTC)
        await session.commit()
    return True
