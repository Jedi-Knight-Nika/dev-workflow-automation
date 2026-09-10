"""Task-owned bounded memory shared by intake and subsequent event wakes."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.task_models import TaskEvent


async def task_memory(session: AsyncSession, task_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id, TaskEvent.source == "supervisor")
            .order_by(TaskEvent.created_at.desc())
            .limit(4)
        )
    ).all()
    return [
        {
            "event": row.event_type,
            "decision": {
                key: value
                for key, value in row.payload.items()
                if key
                in {
                    "action",
                    "assessment",
                    "acceptance_criteria",
                    "physical_object",
                    "intent",
                    "reason",
                    "head_sha",
                    "trigger",
                }
            },
        }
        for row in reversed(rows)
    ]
