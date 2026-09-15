"""Retain a confirmed remote merge SHA when no local merge receipt exists."""

import re
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.task_models import Task, TaskEvent


async def observe_merge(
    session: AsyncSession, task: Task, repository_id: UUID, sha: object
) -> None:
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return
    await session.execute(
        insert(TaskEvent)
        .values(
            task_id=task.id,
            source="github",
            event_type="GITHUB_MERGE_OBSERVED",
            external_event_id=f"merge:{task.id}:{repository_id}:{sha}",
            payload={
                "repository_id": str(repository_id),
                "head_sha": task.current_revision,
                "merge_sha": sha,
            },
        )
        .on_conflict_do_nothing(constraint="uq_event_source_external_id")
    )
