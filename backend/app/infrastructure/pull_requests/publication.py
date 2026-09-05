import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.pull_request_publication import (
    PublishConflict,
    PublishedPullRequest,
    PublishTaskNotFound,
    PublishUnavailable,
)
from app.db.models import Repository, Task
from app.infrastructure.git.workspaces import GitCommandError
from app.infrastructure.pull_requests.operations import publish_pull_request


class SqlAlchemyGitHubPublicationWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish(self, task_id: uuid.UUID) -> PublishedPullRequest:
        task = await self._session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise PublishTaskNotFound("Task not found")
        if task.repository_id is None:
            raise PublishConflict("Task has no repository")
        repository = await self._session.get(Repository, task.repository_id)
        if repository is None:
            raise PublishConflict("Repository is unavailable")
        try:
            result = await publish_pull_request(self._session, task, repository)
        except (GitCommandError, RuntimeError) as exc:
            await self._session.rollback()
            raise PublishUnavailable(str(exc)) from exc
        return PublishedPullRequest(
            number=result.number,
            url=result.url,
            state=result.state,
            head_sha=result.head_sha,
            merged=result.merged,
            merge_commit_sha=result.merge_commit_sha,
        )
