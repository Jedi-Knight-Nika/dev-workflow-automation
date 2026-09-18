"""Explicit task prerequisites, independent of lifecycle and model decisions."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.application.ports.task_dependencies import TaskDependencyView
from app.engineering.infrastructure.task_models import Job, Task, TaskDependency, TaskEvent
from app.platform.scheduling.states import JobState


async def lock_admission(session: AsyncSession) -> None:
    # The existing short dispatch lock also serializes graph edits with claims.
    # No provider calls or execution happen while it is held.
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(741963206)"))


def unmet_dependencies() -> ColumnElement[bool]:
    prerequisite = aliased(Task)
    return (
        select(TaskDependency.task_id)
        .join(prerequisite, prerequisite.id == TaskDependency.prerequisite_id)
        .where(TaskDependency.task_id == Task.id, prerequisite.status != "MERGED")
        .correlate(Task)
        .exists()
    )


async def dependency_views(
    session: AsyncSession, task_ids: Sequence[UUID]
) -> dict[UUID, list[TaskDependencyView]]:
    if not task_ids:
        return {}
    rows = await session.execute(
        select(TaskDependency.task_id, Task.id, Task.title, Task.status)
        .join(Task, Task.id == TaskDependency.prerequisite_id)
        .where(TaskDependency.task_id.in_(task_ids))
        .order_by(Task.id)
    )
    result: dict[UUID, list[TaskDependencyView]] = {}
    for task_id, id, title, status in rows:
        result.setdefault(task_id, []).append(TaskDependencyView(id, title, status))
    return result


class SqlTaskDependencies:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def replace(
        self, task_id: UUID, prerequisites: tuple[UUID, ...], expected: tuple[UUID, ...]
    ) -> None:
        requested = set(prerequisites)
        if len(prerequisites) > 32 or task_id in requested:
            raise ValueError("Choose at most 32 prerequisites; a task cannot depend on itself")
        async with self.sessions.begin() as session:
            if session.get_bind().dialect.name == "postgresql":
                await session.execute(text("SET LOCAL statement_timeout = '3s'"))
            await lock_admission(session)
            task = await session.get(Task, task_id, with_for_update=True)
            if task is None:
                raise LookupError("Task not found")
            existing = set(
                await session.scalars(
                    select(TaskDependency.prerequisite_id).where(TaskDependency.task_id == task_id)
                )
            )
            if existing != set(expected):
                raise ValueError("Prerequisites changed; refresh the task before saving")
            if existing == requested:
                return
            if task.status not in {"NEW", "PAUSED"} or task.archived_at:
                raise ValueError("Pause the task before changing prerequisites")
            busy = await session.scalar(
                select(Job.id)
                .where(Job.task_id == task_id, Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
                .limit(1)
            )
            inference = await session.scalar(
                select(AIRun.id).where(AIRun.task_id == task_id, AIRun.status == "RUNNING").limit(1)
            )
            if busy or inference:
                raise ValueError(
                    "Wait for the current execution to stop before changing prerequisites"
                )
            if requested:
                found = set(await session.scalars(select(Task.id).where(Task.id.in_(requested))))
                if found != requested:
                    raise LookupError("A prerequisite task no longer exists")
                # UNION (not UNION ALL) visits each reachable task once, including
                # shared branches. A cycle cannot be introduced by concurrent edits.
                reachable = select(Task.id).where(Task.id.in_(requested)).cte(recursive=True)
                reachable = reachable.union(
                    select(TaskDependency.prerequisite_id).join(
                        reachable, TaskDependency.task_id == reachable.c.id
                    )
                )
                if await session.scalar(
                    select(reachable.c.id).where(reachable.c.id == task_id).limit(1)
                ):
                    raise ValueError("Prerequisites would create a dependency cycle")
            await session.execute(delete(TaskDependency).where(TaskDependency.task_id == task_id))
            session.add_all(
                TaskDependency(task_id=task_id, prerequisite_id=id) for id in sorted(requested)
            )
            task.updated_at = datetime.now(UTC)
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="dashboard",
                    event_type="TASK_DEPENDENCIES_CHANGED",
                    payload={"dependency_ids": [str(id) for id in sorted(requested)]},
                )
            )
