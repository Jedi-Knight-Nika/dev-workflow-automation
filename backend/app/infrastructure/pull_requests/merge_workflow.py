import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.merge_workflow import MergeContext, MergeOutcome
from app.application.pull_requests.merge_task import MergeConflict
from app.db.models import IndexStatus, Integration, Repository, Task, TaskState, ValidationRecord
from app.domain.pull_requests import ValidationEvidence
from app.infrastructure.integration_access import role_allows_integration
from app.infrastructure.linear_sync import sync_merged_task_to_linear
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth


class SqlAlchemyGitHubMergeWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _client(self) -> GitHubClient:
        integration = await self._session.scalar(
            select(Integration).where(Integration.provider_name == "github")
        )
        if integration is None or integration.encrypted_credentials is None:
            raise MergeConflict("GitHub integration is unavailable")
        if not await role_allows_integration(self._session, "DELIVERER", integration.id):
            raise MergeConflict("GitHub is not enabled on the Deliverer node")
        auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
        return GitHubClient(auth.token, auth.installation)

    async def load_context(self, task_id: uuid.UUID) -> MergeContext | None:
        task = await self._session.get(Task, task_id, with_for_update=True)
        if task is None:
            return None
        if (
            task.pull_request_number is None
            or task.repository_id is None
            or not task.current_revision
        ):
            raise MergeConflict("Task has no publishable pull request")
        repository = await self._session.get(Repository, task.repository_id)
        if repository is None:
            raise MergeConflict("GitHub integration is unavailable")
        records = list(
            (
                await self._session.scalars(
                    select(ValidationRecord)
                    .where(
                        ValidationRecord.task_id == task.id,
                        ValidationRecord.revision == task.current_revision,
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
            pull_request_number=task.pull_request_number,
            expected_revision=task.current_revision,
            evidence=[ValidationEvidence(item.kind, item.name, item.status) for item in records],
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
        task.state = TaskState.MERGED
        task.current_revision = outcome.sha or context.expected_revision
        repository.index_status = IndexStatus.QUEUED
        repository.index_error = None
        await record_event(
            self._session,
            task.id,
            "PULL_REQUEST_MERGED",
            {"merged": outcome.merged, "sha": outcome.sha, "message": outcome.message},
        )
        await self._session.commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._session.get(Task, task_id)
        if task is not None:
            await sync_merged_task_to_linear(self._session, task)

    async def rollback(self) -> None:
        await self._session.rollback()
