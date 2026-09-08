from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.domain.controls import LifecycleAction
from app.engineering.domain.lifecycle import Action, InvalidTransition, TaskStatus
from app.engineering.domain.task import Task
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.enrollment import enroll
from app.engineering.infrastructure.repositories import task_to_domain
from app.engineering.infrastructure.task_models import Task as TaskRecord
from app.engineering.infrastructure.task_models import TaskEvent
from app.platform.configuration.settings import get_settings


class SqlAlchemyTaskLifecycleUnitOfWork:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def change(self, task_id: UUID, action: LifecycleAction, *, actor: str) -> Task:
        async with self._sessions.begin() as session:
            task = await session.get(TaskRecord, task_id, with_for_update=True)
            if task is None:
                raise LookupError("Task not found")
            if action == LifecycleAction.ARCHIVE:
                if task.status not in {TaskStatus.MERGED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
                    raise InvalidTransition("Only terminal tasks can be archived")
                task.archived_at = datetime.now(UTC)
                session.add(
                    TaskEvent(
                        task_id=task.id,
                        source=actor,
                        event_type="TASK_ARCHIVED",
                        payload={"actor": actor},
                    )
                )
            elif (
                action == LifecycleAction.RESUME
                and await session.scalar(
                    select(DeveloperSession.id).where(DeveloperSession.task_id == task.id)
                )
                is None
            ):
                try:
                    await enroll(session, task, get_settings(), actor=actor)
                except ValueError as exc:
                    raise InvalidTransition(str(exc)) from exc
            else:
                command = (
                    Action.RELEASE_TAKEOVER
                    if action == LifecycleAction.RESUME and task.manual_takeover
                    else Action(action.value)
                )
                await control_task(session, task, command, actor=actor)
            await session.flush()
            return task_to_domain(task)


class SqlAlchemyTaskLifecycleUnitOfWorkFactory:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    def __call__(self) -> SqlAlchemyTaskLifecycleUnitOfWork:
        return SqlAlchemyTaskLifecycleUnitOfWork(self._sessions)
