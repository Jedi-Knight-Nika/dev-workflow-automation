from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.domain.review import ReviewedMessage
from app.engineering.infrastructure.models import ReviewCycle, ValidationRun
from app.engineering.infrastructure.task_models import Task


async def review_state(
    session: AsyncSession, task: Task
) -> tuple[tuple[ReviewedMessage, ...], datetime | None]:
    rows = await session.scalars(
        select(ReviewCycle).where(
            ReviewCycle.task_id == task.id, ReviewCycle.head_sha == task.current_revision
        )
    )
    messages = []
    for row in rows:
        saved = row.feedback.get("review_message")
        if isinstance(saved, dict) and all(
            isinstance(saved.get(key), str)
            for key in ("key", "actor_id", "head_sha", "digest", "updated_at")
        ):
            messages.append(ReviewedMessage(**saved, decision=row.decision))
    validated_at = await session.scalar(
        select(func.max(ValidationRun.finished_at)).where(
            ValidationRun.task_id == task.id,
            ValidationRun.head_sha == task.current_revision,
            ValidationRun.requirement_version == task.requirement_version,
            ValidationRun.status == "PASSED",
        )
    )
    return tuple(messages), validated_at
