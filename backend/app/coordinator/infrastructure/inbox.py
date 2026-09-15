"""Normalize task-bound events after existing provider verification and routing."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.coordinator.infrastructure.authority import authorized, coordination_mode
from app.coordinator.infrastructure.models import CoordinatorAction, CoordinatorEvent, HumanRequest
from app.coordinator.infrastructure.queries import latest_human_request
from app.engineering.infrastructure.task_models import Task
from app.platform.configuration.settings import get_settings


async def enqueue(
    session: AsyncSession,
    task: Task,
    *,
    provider: str,
    key: str,
    actor: str,
    body: str,
    kind: str = "MESSAGE_ADDED",
    context: dict[str, Any] | None = None,
) -> bool:
    mode = coordination_mode(provider)
    if mode == "off":
        return False
    if not body.strip() or len(body) > 16000:
        raise ValueError("Coordinator messages must contain 1–16000 characters")
    task = await session.get(Task, task.id, with_for_update=True) or task
    # Dedupe and human-response attachment share the task lock.
    existing = await session.scalar(
        select(CoordinatorEvent.id).where(
            CoordinatorEvent.provider == provider,
            CoordinatorEvent.delivery_key == key,
        )
    )
    if existing:
        return mode == "active"
    if context and context.get("provider_effect_ref"):
        echo = await session.scalar(
            select(CoordinatorAction.id).where(
                CoordinatorAction.provider_effect_ref == str(context["provider_effect_ref"]),
                CoordinatorAction.task_id == task.id,
            )
        )
        if echo:
            return mode == "active"
    # Some providers emit the webhook before the POST response supplies its ID.
    # Match only the configured integration identity while an identical outbox
    # message is in flight; a human quoting the bot must still wake coordination.
    from app.platform.integrations.models import Integration

    integration = (
        await session.scalar(select(Integration).where(Integration.provider_name == provider))
        if provider not in {"dashboard", "engineering"}
        else None
    )
    own_actor = (integration.configuration or {}).get("identity_id") if integration else None
    if own_actor and str(own_actor) == actor:
        pending = await session.scalar(
            select(CoordinatorAction)
            .where(
                CoordinatorAction.task_id == task.id,
                CoordinatorAction.status.in_(["SENDING", "UNKNOWN", "RECONCILING", "EXECUTED"]),
                CoordinatorAction.arguments["provider"].as_string() == provider,
                CoordinatorAction.arguments["message"].as_string() == body,
            )
            .order_by(CoordinatorAction.created_at.desc())
            .limit(1)
        )
        if pending:
            effect = str((context or {}).get("provider_effect_ref") or "")
            if effect:
                pending.provider_effect_ref, pending.status = effect, "EXECUTED"
            session.add(
                CoordinatorEvent(
                    task_id=task.id,
                    provider=provider,
                    delivery_key=key,
                    actor=actor,
                    kind="EFFECT_CONFIRMED",
                    status="ECHO",
                    context={"action_id": str(pending.id)},
                )
            )
            return mode == "active"
    details = {**(context or {}), "body": body[:8000], "body_truncated": len(body) > 8000}
    event = CoordinatorEvent(
        task_id=task.id,
        provider=provider,
        delivery_key=key,
        actor=actor,
        kind=kind,
        context=details,
        available_at=datetime.now(UTC)
        + timedelta(seconds=get_settings().coordinator_debounce_seconds),
    )
    if not await authorized(session, task, event):
        event.status = "UNAUTHORIZED"
        session.add(event)
        return mode == "active"
    if mode == "active" and not details.get("human_request_id") and body.strip():
        # Only the same task-bound conversation (or its dashboard) can answer.
        human = await session.scalar(
            latest_human_request(task)
            .join(CoordinatorAction, CoordinatorAction.run_id == HumanRequest.run_id)
            .where(
                or_(
                    CoordinatorAction.arguments["provider"].as_string() == provider,
                    true()
                    if provider == "dashboard"
                    else CoordinatorAction.arguments["provider"].as_string() == provider,
                ),
            )
        )
        if human:
            details["human_request_id"] = str(human.id)
    if mode == "active" and details.get("human_request_id"):
        human = await session.scalar(
            select(HumanRequest)
            .where(
                HumanRequest.task_id == task.id,
                HumanRequest.status.in_(["OPEN", "ANSWERED"]),
                HumanRequest.id == UUID(str(details["human_request_id"])),
            )
            .with_for_update()
        )
        if (
            human
            and body.strip()
            and (human.requirement_revision, human.lifecycle_revision)
            == (task.requirement_version, task.lifecycle_version)
        ):
            if human.status == "OPEN":
                human.answer, human.status = body[:8000], "ANSWERED"
                human.answered_at = datetime.now(UTC)
            kind = "HUMAN_RESPONSE"
            details["human_request_id"] = str(human.id)
    event.kind, event.context = kind, details
    session.add(event)
    return mode == "active"


async def human_response(session: AsyncSession, task: Task, identifier: UUID, answer: str) -> None:
    from app.teams.infrastructure.team_models import Team

    team = await session.get(Team, task.team_id) if task.team_id else None
    if (
        not team
        or not team.enabled
        or team.execution_paused
        or team.archived_at
        or task.archived_at
        or task.manual_takeover
        or task.status in {"PAUSED", "MERGED", "FAILED", "CANCELLED"}
    ):
        raise ValueError("Task or Team is suspended; restore execution before continuing")
    human = await session.get(HumanRequest, identifier, with_for_update=True)
    if not human or human.task_id != task.id:
        raise LookupError("Human request not found")
    if human.status != "OPEN":
        raise ValueError("This request has already been answered or cancelled")
    if (human.requirement_revision, human.lifecycle_revision) != (
        task.requirement_version,
        task.lifecycle_version,
    ):
        raise ValueError("Task changed; refresh before responding")
    if coordination_mode("dashboard") != "active":
        raise ValueError("Active dashboard coordination is required to send and continue")
    await enqueue(
        session,
        task,
        provider="dashboard",
        key=f"human:{identifier}",
        actor="local-operator",
        body=answer,
        kind="HUMAN_RESPONSE",
        context={"human_request_id": str(identifier)},
    )


async def notify_engineering(session: AsyncSession, task: Task, action: str) -> None:
    previous = await session.scalar(
        select(CoordinatorEvent)
        .where(
            CoordinatorEvent.task_id == task.id,
            CoordinatorEvent.provider != "engineering",
            CoordinatorEvent.status.not_in(["UNAUTHORIZED", "ECHO"]),
        )
        .order_by(CoordinatorEvent.created_at.desc())
        .limit(1)
    )
    if not previous or coordination_mode(previous.provider) == "off":
        return
    session.add(
        CoordinatorEvent(
            task_id=task.id,
            provider="engineering",
            actor="engineering",
            delivery_key=f"{task.id}:{task.lifecycle_version}",
            kind={
                "BLOCK": "ENGINEERING_BLOCKED",
                "PUBLISHED": "PUBLICATION_COMPLETED",
                "MERGED": "MERGE_STATE_CHANGED",
                "START": "ENGINEERING_STARTED",
                "IMPLEMENTED": "ENGINEERING_COMPLETED",
                "VALIDATION_PASSED": "VALIDATION_COMPLETED",
                "VALIDATION_FAILED": "VALIDATION_COMPLETED",
                "CANCEL": "TASK_CANCELLED",
            }.get(action, "ENGINEERING_UPDATED"),
            context={
                "body": f"{action}: {task.status} / {task.stage}. PR: {task.pull_request_url or 'not published'}. Wait reason: {task.wait_reason}",
                "reply_provider": previous.provider,
            },
        )
    )


async def notify_observation(
    session: AsyncSession,
    task: Task,
    *,
    kind: str,
    key: str,
    provider: str,
    body: str,
) -> None:
    """Trusted reconciled facts can wake communication, never competing engineering work."""
    if coordination_mode(provider) == "off":
        return
    delivery_key = f"observation:{task.id}:{key}"
    if await session.scalar(
        select(CoordinatorEvent.id).where(
            CoordinatorEvent.provider == "engineering",
            CoordinatorEvent.delivery_key == delivery_key,
        )
    ):
        return
    session.add(
        CoordinatorEvent(
            task_id=task.id,
            provider="engineering",
            actor="engineering",
            delivery_key=delivery_key,
            kind=kind,
            context={"body": body[:8000], "reply_provider": provider},
            available_at=datetime.now(UTC)
            + timedelta(seconds=get_settings().coordinator_debounce_seconds),
        )
    )
