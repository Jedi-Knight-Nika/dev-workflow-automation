from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, ReviewCycle, Task, TaskMessage


async def tracker_comment(
    session: AsyncSession,
    task: Task,
    provider: str,
    event_id: str,
    payload: dict[str, Any],
    *,
    routed_actor: bool = False,
) -> None:
    # Signed webhook != authorization to change repository requirements. Preserve
    # tracker prose for operator attention; only configured source owners may route it.
    session.add(
        TaskMessage(
            task_id=task.id,
            author_type="EXTERNAL",
            author_name=str(payload.get("author") or provider)[:120],
            kind="COMMENT",
            body=str(payload.get("raw_text") or "")[:8000],
            context={
                "provider": provider,
                "event_id": event_id,
                "routing": "operator-context-required",
            },
        )
    )
    actor = str(payload.get("actor_id") or "")
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == provider)
    )
    allowed = (integration.configuration or {}).get("v2_actor_ids", []) if integration else []
    if not actor or (not routed_actor and actor not in allowed) or task.execution_version != 2:
        return
    key = f"{provider}:{event_id}"
    if await session.scalar(
        select(ReviewCycle.id).where(
            ReviewCycle.task_id == task.id, ReviewCycle.external_event_id == key
        )
    ):
        return
    body = str(payload.get("raw_text") or "")
    if not 0 < len(body) <= 16000:
        return
    session.add(
        ReviewCycle(
            task_id=task.id,
            external_event_id=key,
            head_sha=task.current_revision or "",
            actor=actor,
            decision="CLASSIFY_PENDING",
            feedback={
                "body": body,
                "provider": provider,
                "task_reference": task.external_key or str(task.id),
            },
        )
    )
