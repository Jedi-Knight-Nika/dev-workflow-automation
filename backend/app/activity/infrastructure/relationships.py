"""Bounded relationship reads over public activity metadata."""

from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.infrastructure.models import ActivityEvent


def summary(event: ActivityEvent) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "kind": event.kind,
        "occurred_at": event.occurred_at,
        "actor": event.actor,
        "actor_type": event.actor_type,
        "task_id": str(event.task_id),
        "payload": event.payload,
    }


async def parents_for(
    session: AsyncSession, events: list[ActivityEvent], through: int
) -> dict[int, list[dict[str, Any]]]:
    identities = {
        (ref["source_type"], ref["source_id"]) for event in events for ref in event.references
    }
    if not identities:
        return {}
    parents = {
        (p.source_type, p.source_id): p
        for p in await session.scalars(
            select(ActivityEvent).where(
                tuple_(ActivityEvent.source_type, ActivityEvent.source_id).in_(identities),
                ActivityEvent.sequence <= through,
            )
        )
    }
    result = {}
    for event in events:
        result[event.sequence] = [
            {**summary(parent), "relationship": ref["relationship"]}
            for ref in event.references
            if (parent := parents.get((ref["source_type"], ref["source_id"]))) is not None
            and parent.task_id == event.task_id
            and parent.sequence != event.sequence
        ]
    return result


async def inspect_related(
    session: AsyncSession, event: ActivityEvent, through: int
) -> dict[str, Any]:
    children = list(
        await session.scalars(
            select(ActivityEvent)
            .where(
                ActivityEvent.task_id == event.task_id,
                ActivityEvent.sequence <= through,
                ActivityEvent.references.contains(
                    [{"source_type": event.source_type, "source_id": event.source_id}]
                ),
            )
            .order_by(ActivityEvent.occurred_at, ActivityEvent.sequence)
            .limit(51)
        )
    )
    checks = []
    if sha := event.payload.get("head_sha"):
        query = select(ActivityEvent).where(
            ActivityEvent.task_id == event.task_id,
            ActivityEvent.sequence <= through,
            ActivityEvent.kind == "VALIDATION_CHECK_COMPLETED",
            ActivityEvent.payload["head_sha"].astext == sha,
        )
        if version := event.payload.get("requirement_version"):
            query = query.where(
                ActivityEvent.payload["requirement_version"].as_integer() == version
            )
        checks = list(
            await session.scalars(
                query.order_by(ActivityEvent.occurred_at, ActivityEvent.sequence).limit(51)
            )
        )
    return {
        "children": [summary(child) for child in children[:50]],
        "checks": [summary(check) for check in checks[:50]],
        "truncated": len(children) > 50 or len(checks) > 50,
        "file_status": event.file_status,
        "file_attempts": event.file_attempts,
        "file_retry_at": event.file_retry_at,
    }
