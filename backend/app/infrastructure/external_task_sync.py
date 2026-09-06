from datetime import UTC, datetime

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExternalTaskSnapshot, Integration, Task, TaskEvent, TaskState
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.security.crypto import cipher
from app.integrations.linear import LinearClient
from app.integrations.trello import TrelloClient

STATE_CONFIGURATION: dict[TaskState, tuple[str, str]] = {
    TaskState.NEW: ("todo", "Todo"),
    TaskState.PLANNING: ("in_progress", "In Progress"),
    TaskState.PLAN_READY: ("in_progress", "In Progress"),
    TaskState.QUEUED_FOR_EXECUTION: ("in_progress", "In Progress"),
    TaskState.IMPLEMENTING: ("in_progress", "In Progress"),
    TaskState.LOCAL_VALIDATION: ("in_progress", "In Progress"),
    TaskState.INTERNAL_REVIEW: ("in_review", "In Review"),
    TaskState.WAITING_GITHUB: ("in_review", "In Review"),
    TaskState.READY_TO_MERGE: ("in_review", "In Review"),
    TaskState.CONTEXT_PENDING: ("blocked", "Blocked"),
    TaskState.NEEDS_HUMAN: ("blocked", "Blocked"),
    TaskState.FAILED: ("blocked", "Blocked"),
    TaskState.MERGED: ("ready_for_testing", "Ready for Testing"),
    TaskState.CANCELLED: ("done", "Done"),
}

PROVIDER_TARGET_SUFFIX = {"linear": "state_id", "trello": "list_id"}


def external_status_configuration_key(provider: str, state: TaskState) -> str | None:
    mapping = STATE_CONFIGURATION.get(state)
    suffix = PROVIDER_TARGET_SUFFIX.get(provider)
    if mapping is None or suffix is None:
        return None
    return f"{mapping[0]}_{suffix}"


async def sync_external_task_state(session: AsyncSession, task: Task) -> bool:
    """Mirror an internal Task state to the task-management system it came from."""
    mapping = STATE_CONFIGURATION.get(task.state)
    if mapping is None:
        return False
    _, status_label = mapping
    snapshot = await session.scalar(
        select(ExternalTaskSnapshot)
        .where(
            ExternalTaskSnapshot.task_id == task.id,
            ExternalTaskSnapshot.provider.in_(PROVIDER_TARGET_SUFFIX),
        )
        .order_by(ExternalTaskSnapshot.synchronized_at.desc())
    )
    if snapshot is None:
        return False
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == snapshot.provider)
    )
    configuration_key = external_status_configuration_key(snapshot.provider, task.state)
    if configuration_key is None:
        return False
    target_id = integration.configuration.get(configuration_key) if integration else None
    if integration is None or integration.encrypted_credentials is None or not target_id:
        await _record_skipped(session, task, snapshot.provider, status_label, configuration_key)
        return False
    target_id = str(target_id)
    if snapshot.state_id == target_id:
        return True
    if await _already_synchronized(session, task, snapshot.provider, task.state, target_id):
        return True
    try:
        credential = cipher.decrypt(integration.encrypted_credentials)
        if snapshot.provider == "linear":
            await LinearClient(credential).update_issue_state(snapshot.external_id, target_id)
        else:
            await TrelloClient(credential).update_card_list(snapshot.external_id, target_id)
    except (httpx.HTTPError, InvalidToken, RuntimeError, TypeError, ValueError) as exc:
        await record_event(
            session,
            task.id,
            "EXTERNAL_STATE_SYNC_FAILED",
            {"provider": snapshot.provider, "error": str(exc)[:1000]},
            source=snapshot.provider,
        )
        await session.commit()
        return False

    snapshot.state_id = target_id
    snapshot.synchronized_at = datetime.now(UTC)
    if snapshot.provider == "trello":
        snapshot.raw_payload = {**snapshot.raw_payload, "idList": target_id}
    elif isinstance(snapshot.raw_payload.get("state"), dict):
        snapshot.raw_payload = {
            **snapshot.raw_payload,
            "state": {**snapshot.raw_payload["state"], "id": target_id},
        }
    await record_event(
        session,
        task.id,
        "EXTERNAL_STATE_SYNCED",
        {
            "provider": snapshot.provider,
            "external_id": snapshot.external_id,
            "external_status_id": target_id,
            "internal_state": task.state.value,
        },
        source=snapshot.provider,
    )
    await session.commit()
    return True


async def _already_synchronized(
    session: AsyncSession,
    task: Task,
    provider: str,
    state: TaskState,
    target_id: str,
) -> bool:
    latest = await session.scalar(
        select(TaskEvent)
        .where(
            TaskEvent.task_id == task.id,
            TaskEvent.event_type == "EXTERNAL_STATE_SYNCED",
            TaskEvent.source == provider,
        )
        .order_by(TaskEvent.created_at.desc())
    )
    return bool(
        latest
        and latest.payload.get("internal_state") == state.value
        and latest.payload.get("external_status_id") == target_id
    )


async def _record_skipped(
    session: AsyncSession,
    task: Task,
    provider: str,
    status_label: str,
    configuration_key: str,
) -> None:
    await record_event(
        session,
        task.id,
        "EXTERNAL_STATE_SYNC_SKIPPED",
        {
            "provider": provider,
            "reason": f"{status_label} mapping ({configuration_key}) is not configured",
        },
        source=provider,
    )
    await session.commit()
