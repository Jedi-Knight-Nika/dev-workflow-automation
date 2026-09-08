from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.job_queue import record_event, request_execution
from app.engineering.infrastructure.task_models import Task
from app.intake.domain.eligibility import linear_eligible
from app.intake.domain.linear import (
    configured_repository_id,
    linear_comment,
    linear_datetime,
    linear_priority,
)
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.intake.infrastructure.webhook_models import WebhookDelivery
from app.platform.integrations.models import Integration
from app.platform.integrations.retry import DeliveryRetryPolicy
from app.teams.infrastructure.routing import assign_routed_team


async def process_linear_delivery(session: AsyncSession, delivery: WebhookDelivery) -> None:
    payload = delivery.payload
    comment = linear_comment(payload)
    if comment:
        comment_identifier, intake_payload = comment
        task = await session.scalar(select(Task).where(Task.external_key == comment_identifier))
        if task is None:
            delivery.status = "IGNORED"
            return
        from app.intake.infrastructure.tracker_comments import tracker_comment

        await tracker_comment(session, task, "linear", delivery.delivery_id, intake_payload)
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
    task = await session.scalar(select(Task).where(Task.external_key == str(identifier)))
    if payload.get("action") == "remove" or data.get("archivedAt"):
        if task:
            if task.status not in {"MERGED", "CANCELLED", "FAILED"}:
                from app.engineering.domain.lifecycle import Action
                from app.engineering.infrastructure.controls import control_task

                await control_task(session, task, Action.CANCEL, actor="linear")
            await record_event(session, task.id, "LINEAR_ISSUE_REMOVED", {}, source="linear")
        delivery.status = "PROCESSED"
        return
    assignee_id = str((data.get("assignee") or {}).get("id"))
    state_id = str((data.get("state") or {}).get("id"))
    triggered = linear_eligible(configuration, assignee_id, state_id)
    if task is None and (not triggered):
        delivery.status = "IGNORED"
        return
    if task is None:
        task = Task(
            external_key=str(identifier),
            title=str(data.get("title") or identifier),
            description=str(data.get("description")),
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
        await request_execution(session, task, actor="tracker:ingestion")
    else:
        from app.intake.infrastructure.v2_events import requirements_changed

        await requirements_changed(
            session,
            task,
            str(data.get("title") or task.title),
            str(
                data.get("description") if data.get("description") is not None else task.description
            ),
            source="linear",
        )
        task.title = str(data.get("title") or task.title)
        if data.get("description") is not None:
            task.description = str(data["description"])
        task.priority = linear_priority(data.get("priority"))
        await record_event(
            session,
            task.id,
            "TASK_UPDATED_FROM_LINEAR",
            {"action": payload.get("action")},
            source="linear",
        )
    linear_issue_id = str(data.get("id"))
    task.due_at = linear_datetime(data.get("dueDate"))
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
        snapshot.assignee_id = assignee_id
        snapshot.state_id = state_id
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
