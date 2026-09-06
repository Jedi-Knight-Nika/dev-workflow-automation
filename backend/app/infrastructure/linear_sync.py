import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, Task, TaskEvent, TaskState
from app.infrastructure.integration_access import role_allows_integration
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.security.crypto import cipher
from app.integrations.linear import LinearClient

LINEAR_STATE_CONFIGURATION: dict[TaskState, tuple[str, str]] = {
    TaskState.NEW: ("todo_state_id", "Todo"),
    TaskState.PLANNING: ("in_progress_state_id", "In Progress"),
    TaskState.PLAN_READY: ("in_progress_state_id", "In Progress"),
    TaskState.QUEUED_FOR_EXECUTION: ("in_progress_state_id", "In Progress"),
    TaskState.IMPLEMENTING: ("in_progress_state_id", "In Progress"),
    TaskState.LOCAL_VALIDATION: ("in_progress_state_id", "In Progress"),
    TaskState.INTERNAL_REVIEW: ("in_review_state_id", "In Review"),
    TaskState.WAITING_GITHUB: ("in_review_state_id", "In Review"),
    TaskState.READY_TO_MERGE: ("in_review_state_id", "In Review"),
    TaskState.CONTEXT_PENDING: ("blocked_state_id", "Blocked"),
    TaskState.NEEDS_HUMAN: ("blocked_state_id", "Blocked"),
    TaskState.FAILED: ("blocked_state_id", "Blocked"),
    TaskState.MERGED: ("ready_for_testing_state_id", "Ready for Testing"),
    TaskState.CANCELLED: ("done_state_id", "Done"),
}


async def sync_task_to_linear(
    session: AsyncSession,
    task: Task,
    *,
    configuration_key: str,
    success_event: str,
    state_label: str,
    success_payload: dict[str, str] | None = None,
) -> bool:
    if not task.external_key:
        await record_event(session, task.id, "LINEAR_SYNC_SKIPPED", {"reason": "No issue key"})
        await session.commit()
        return False
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "linear")
    )
    state_id = integration.configuration.get(configuration_key) if integration else None
    if not integration or not integration.encrypted_credentials or not state_id:
        await record_event(
            session,
            task.id,
            "LINEAR_SYNC_SKIPPED",
            {"reason": f"Linear credential or {state_label} state is not configured"},
        )
        await session.commit()
        return False
    if not await role_allows_integration(session, "DELIVERER", integration.id):
        await record_event(
            session,
            task.id,
            "LINEAR_SYNC_SKIPPED",
            {"reason": "Linear is not enabled on the Deliverer node"},
        )
        await session.commit()
        return False
    try:
        client = LinearClient(cipher.decrypt(integration.encrypted_credentials))
        await client.update_issue_state(task.external_key, str(state_id))
    except (httpx.HTTPError, InvalidToken, RuntimeError) as exc:
        await record_event(
            session, task.id, "LINEAR_SYNC_FAILED", {"error": str(exc)[:1000]}, source="linear"
        )
        await session.commit()
        return False
    await record_event(
        session,
        task.id,
        success_event,
        {
            "issue": task.external_key,
            "state_id": str(state_id),
            **(success_payload or {}),
        },
        source="linear",
    )
    await session.commit()
    return True


async def sync_published_task_to_linear(session: AsyncSession, task: Task) -> bool:
    return await sync_task_to_linear(
        session,
        task,
        configuration_key="in_review_state_id",
        success_event="LINEAR_IN_REVIEW",
        state_label="In Review",
    )


async def sync_merged_task_to_linear(session: AsyncSession, task: Task) -> bool:
    return await sync_task_to_linear(
        session,
        task,
        configuration_key="ready_for_testing_state_id",
        success_event="LINEAR_READY_FOR_TESTING",
        state_label="Ready for Testing",
    )


async def sync_current_task_state_to_linear(session: AsyncSession, task: Task) -> bool:
    mapping = LINEAR_STATE_CONFIGURATION.get(task.state)
    if mapping is None:
        return False
    configuration_key, state_label = mapping
    latest = await session.scalar(
        select(TaskEvent)
        .where(TaskEvent.task_id == task.id, TaskEvent.event_type == "LINEAR_STATE_SYNCED")
        .order_by(TaskEvent.created_at.desc())
    )
    if latest and latest.payload.get("internal_state") == task.state.value:
        return True
    synced = await sync_task_to_linear(
        session,
        task,
        configuration_key=configuration_key,
        success_event="LINEAR_STATE_SYNCED",
        state_label=state_label,
        success_payload={"internal_state": task.state.value},
    )
    return synced
