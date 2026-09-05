import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.workspace_workflow import (
    WorkspaceConflict,
    WorkspaceTaskNotFound,
    WorkspaceUnavailable,
)
from app.db.models import Repository, Task
from app.domain.tasks import Task as DomainTask
from app.infrastructure.git.workspaces import GitCommandError, prepare_workspace
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.persistence.repositories import task_to_domain


class SqlAlchemyGitWorkspaceWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prepare(self, task_id: uuid.UUID) -> DomainTask:
        task = await self._session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise WorkspaceTaskNotFound("Task not found")
        if task.repository_id is None:
            raise WorkspaceConflict("Task has no selected repository")
        repository = await self._session.get(Repository, task.repository_id)
        if repository is None or not repository.enabled:
            raise WorkspaceConflict("Repository is unavailable")
        try:
            await prepare_workspace(self._session, task, repository)
            await record_event(
                self._session,
                task.id,
                "WORKSPACE_READY",
                {"branch": task.branch_name, "revision": task.current_revision},
            )
            await self._session.commit()
            await self._session.refresh(task)
        except GitCommandError as exc:
            await self._session.rollback()
            raise WorkspaceUnavailable(f"Git workspace failed: {exc}") from exc
        return task_to_domain(task)
