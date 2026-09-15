"""Current source requirement plus durable, authorized conversational amendments."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.task_models import Task, TaskEvent

ACCEPTED_REQUIREMENT = "COORDINATOR_REQUIREMENT_ACCEPTED"


async def current_requirement(
    session: AsyncSession, task: Task, *, addition: dict[str, Any] | None = None
) -> str:
    rows = list(
        await session.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task.id,
                TaskEvent.source == "coordinator",
                TaskEvent.event_type == ACCEPTED_REQUIREMENT,
            )
            .order_by(TaskEvent.id)
            .limit(101)
        )
    )
    amendments = [row.payload for row in rows]
    if addition is not None:
        amendments.append(addition)
    if len(amendments) > 100:
        raise ValueError("Requirement history exceeds its execution bound; consolidate explicitly")
    result = f"{task.title}\n\n{task.description}".strip()
    if amendments:
        result += "\n\nAuthorized clarifications (chronological; preserve the original objective):"
    for amendment in amendments:
        result += "\n\n" + str(amendment["request"])
        for invariant in amendment.get("invariants", []):
            result += "\n- " + invariant
    # Leave the existing prompt compiler responsible for additional context bounds.
    if len(result) > 23500:
        raise ValueError("Complete requirement and clarifications exceed the execution input bound")
    return result
