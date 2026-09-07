import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.merge_workflow import MergeContext, MergeOutcome
from app.application.pull_requests.merge_task import MergeConflict
from app.db.models import (
    IndexStatus,
    Integration,
    Repository,
    Task,
    TaskRepositoryScope,
    TaskState,
    ValidationRecord,
)
from app.domain.pull_requests import ValidationEvidence
from app.infrastructure.external_task_sync import sync_external_task_state
from app.infrastructure.integration_access import role_allows_integration
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth


class SqlAlchemyGitHubMergeWorkflow:
    def __init__(self, session: AsyncSession, repository_id: uuid.UUID | None = None) -> None:
        self._session = session
        self._repository_id = repository_id
        self._team_id: uuid.UUID | None = None

    async def _client(self) -> GitHubClient:
        integration = await self._session.scalar(
            select(Integration).where(Integration.provider_name == "github")
        )
        if integration is None or integration.encrypted_credentials is None:
            raise MergeConflict("GitHub integration is unavailable")
        if not await role_allows_integration(
            self._session, "DELIVERER", integration.id, self._team_id
        ):
            raise MergeConflict("GitHub is not enabled on the Deliverer node")
        auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
        return GitHubClient(auth.token, auth.installation)

    async def load_context(self, task_id: uuid.UUID) -> MergeContext | None:
        task = await self._session.get(Task, task_id, with_for_update=True)
        if task is None:
            return None
        self._team_id = task.team_id
        scope = await self._session.scalar(
            select(TaskRepositoryScope).where(
                TaskRepositoryScope.task_id == task.id,
                TaskRepositoryScope.repository_id == (self._repository_id or task.repository_id),
            )
        )
        repository_id = scope.repository_id if scope else task.repository_id
        if self._repository_id and scope is None and self._repository_id != task.repository_id:
            raise MergeConflict("Requested repository is outside this task's pull-request scope")
        number = scope.pull_request_number if scope else task.pull_request_number
        revision = scope.current_revision if scope else task.current_revision
        if number is None or repository_id is None or not revision:
            raise MergeConflict("Task has no publishable pull request")
        repository = await self._session.get(Repository, repository_id)
        if repository is None:
            raise MergeConflict("GitHub integration is unavailable")
        records = list(
            (
                await self._session.scalars(
                    select(ValidationRecord)
                    .where(
                        ValidationRecord.task_id == task.id,
                        ValidationRecord.revision == revision,
                    )
                    .order_by(ValidationRecord.created_at)
                )
            ).all()
        )
        return MergeContext(
            task_id=task.id,
            repository_id=repository.id,
            owner=repository.owner,
            repository=repository.name,
            pull_request_number=number,
            expected_revision=revision,
            evidence=[
                ValidationEvidence(item.kind, item.name, item.status)
                for item in records
                if item.payload.get("repository_id") == str(repository.id)
                or not item.payload.get("repository_id")
                and repository.id == task.repository_id
            ],
            scope_id=scope.id if scope else None,
        )

    async def current_head(self, context: MergeContext) -> str:
        pull_request = await (await self._client()).get_pull_request(
            context.owner, context.repository, context.pull_request_number
        )
        return pull_request.head_sha

    async def reject_stale_head(self, context: MergeContext, actual_revision: str) -> None:
        task = await self._session.get(Task, context.task_id, with_for_update=True)
        if task is None:
            raise RuntimeError("Task disappeared during merge")
        if context.scope_id:
            scope = await self._session.get(TaskRepositoryScope, context.scope_id)
            if scope:
                scope.current_revision = actual_revision
                if scope.is_primary:
                    task.current_revision = actual_revision
        else:
            task.current_revision = actual_revision
        task.state = TaskState.WAITING_GITHUB
        await record_event(
            self._session,
            task.id,
            "MERGE_REJECTED_STALE_SHA",
            {"expected": context.expected_revision, "actual": actual_revision},
        )
        await self._session.commit()

    async def merge(self, context: MergeContext) -> MergeOutcome:
        result = await (await self._client()).merge_pull_request(
            context.owner,
            context.repository,
            context.pull_request_number,
            context.expected_revision,
        )
        return MergeOutcome(result.merged, result.sha, result.message)

    async def complete(self, context: MergeContext, outcome: MergeOutcome) -> None:
        task = await self._session.get(Task, context.task_id, with_for_update=True)
        repository = await self._session.get(Repository, context.repository_id)
        if task is None or repository is None:
            raise RuntimeError("Task or repository disappeared during merge")
        if context.scope_id:
            scope = await self._session.get(TaskRepositoryScope, context.scope_id)
            if scope:
                scope.merged_at = datetime.now(UTC)
                scope.merge_commit_sha = outcome.sha
        await self._session.flush()
        pending = await self._session.scalar(
            select(TaskRepositoryScope.id)
            .where(
                TaskRepositoryScope.task_id == task.id,
                TaskRepositoryScope.changed.is_(True),
                TaskRepositoryScope.merged_at.is_(None),
            )
            .limit(1)
        )
        task.state = TaskState.WAITING_GITHUB if pending else TaskState.MERGED
        if pending is None:
            task.completed_at = datetime.now(UTC)
        if context.repository_id == task.repository_id:
            task.current_revision = outcome.sha or context.expected_revision
        repository.index_status = IndexStatus.QUEUED
        repository.index_error = None
        await record_event(
            self._session,
            task.id,
            "PULL_REQUEST_MERGED",
            {
                "merged": outcome.merged,
                "sha": outcome.sha,
                "message": outcome.message,
                "repository_id": str(context.repository_id),
                "pull_request_number": context.pull_request_number,
            },
        )
        await self._session.commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._session.get(Task, task_id)
        if task is not None:
            await sync_external_task_state(self._session, task)

    async def rollback(self) -> None:
        await self._session.rollback()
