import builtins
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
    ManagedRepositoryNotFound,
    RepositoryDependencies,
    RepositoryView,
)
from app.db.models import AccountSettings, IndexStatus, Integration, Repository, Task, Team
from app.domain.tasks import TaskState

TERMINAL_TASK_STATES = {TaskState.CANCELLED, TaskState.FAILED, TaskState.MERGED}


class SqlAlchemyRepositoryManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _code_status(item: Repository) -> str:
        if item.archived_at is not None or not item.enabled:
            return "DISABLED"
        if item.local_path and item.latest_sha:
            return "READY"
        if item.index_status in {IndexStatus.QUEUED, IndexStatus.INDEXING}:
            return "UPDATING"
        if item.index_status is IndexStatus.FAILED:
            return "CANNOT_FETCH"
        return "NOT_PREPARED"

    @staticmethod
    def _knowledge_status(item: Repository) -> str:
        if item.archived_at is not None or not item.enabled:
            return "DISABLED"
        if item.index_status is IndexStatus.READY:
            return "OUT_OF_DATE" if item.latest_sha != item.indexed_sha else "READY"
        if item.index_status in {IndexStatus.QUEUED, IndexStatus.INDEXING}:
            return "INDEXING"
        if item.index_status is IndexStatus.FAILED:
            return "FAILED"
        return "NOT_PREPARED"

    async def _context(
        self, repository_ids: builtins.list[uuid.UUID]
    ) -> tuple[
        dict[uuid.UUID, int],
        dict[uuid.UUID, tuple[int, int, datetime | None]],
        builtins.list[Team],
    ]:
        if not repository_ids:
            return {}, {}, []
        chunk_rows = (
            await self._session.execute(
                text(
                    """SELECT repository_id, count(*) AS count
                    FROM knowledge_chunks WHERE repository_id = ANY(:repository_ids)
                    GROUP BY repository_id"""
                ),
                {"repository_ids": repository_ids},
            )
        ).mappings()
        chunks = {row["repository_id"]: int(row["count"]) for row in chunk_rows}
        task_rows = (
            await self._session.execute(
                select(
                    Task.repository_id,
                    func.count(Task.id)
                    .filter(Task.state.not_in(TERMINAL_TASK_STATES))
                    .label("active_tasks"),
                    func.count(Task.id)
                    .filter(
                        Task.state.not_in(TERMINAL_TASK_STATES),
                        Task.workspace_path.is_not(None),
                    )
                    .label("active_workspaces"),
                    func.max(Task.updated_at).label("last_activity"),
                )
                .where(Task.repository_id.in_(repository_ids), Task.archived_at.is_(None))
                .group_by(Task.repository_id)
            )
        ).mappings()
        tasks = {
            row["repository_id"]: (
                int(row["active_tasks"]),
                int(row["active_workspaces"]),
                row["last_activity"],
            )
            for row in task_rows
        }
        teams = list(
            (
                await self._session.scalars(
                    select(Team).where(Team.archived_at.is_(None)).order_by(Team.name)
                )
            ).all()
        )
        return chunks, tasks, teams

    def _view(
        self,
        item: Repository,
        chunks: dict[uuid.UUID, int],
        tasks: dict[uuid.UUID, tuple[int, int, datetime | None]],
        teams: builtins.list[Team],
    ) -> RepositoryView:
        active_tasks, active_workspaces, last_activity = tasks.get(item.id, (0, 0, None))
        teams_count = sum(str(item.id) in (team.repository_ids or []) for team in teams)
        return RepositoryView(
            item.id,
            item.provider,
            item.external_repo_id,
            item.owner,
            item.name,
            item.clone_url,
            item.default_branch,
            item.enabled,
            item.local_path,
            item.latest_sha,
            item.indexed_sha,
            item.indexed_at,
            item.index_status.value,
            item.index_error,
            item.updated_at,
            "CLONED" if item.local_path and item.latest_sha else "NOT_CLONED",
            chunks.get(item.id, 0),
            item.archived_at,
            self._code_status(item),
            self._knowledge_status(item),
            teams_count,
            active_tasks,
            active_workspaces,
            last_activity or item.updated_at,
        )

    async def _views(self, items: builtins.list[Repository]) -> builtins.list[RepositoryView]:
        chunks, tasks, teams = await self._context([item.id for item in items])
        return [self._view(item, chunks, tasks, teams) for item in items]

    async def list(self, include_archived: bool = False) -> builtins.list[RepositoryView]:
        statement = select(Repository)
        if not include_archived:
            statement = statement.where(Repository.archived_at.is_(None))
        items = list(
            (
                await self._session.scalars(statement.order_by(Repository.owner, Repository.name))
            ).all()
        )
        return await self._views(items)

    async def create(self, command: CreateRepositoryCommand) -> RepositoryView:
        return (await self.import_batch([command], prepare_knowledge=True))[0]

    async def import_batch(
        self, commands: builtins.list[CreateRepositoryCommand], prepare_knowledge: bool
    ) -> builtins.list[RepositoryView]:
        if not commands:
            return []
        keys = {(command.provider, command.external_repo_id) for command in commands}
        if len(keys) != len(commands):
            raise ManagedRepositoryConflict("Repository selection contains duplicates")
        existing = list(
            (
                await self._session.scalars(
                    select(Repository).where(
                        Repository.provider.in_({item[0] for item in keys}),
                        Repository.external_repo_id.in_({item[1] for item in keys}),
                    )
                )
            ).all()
        )
        if any((item.provider, item.external_repo_id) in keys for item in existing):
            raise ManagedRepositoryConflict("One or more repositories are already imported")
        settings = await self._session.get(AccountSettings, "default")
        auto_index = settings is None or settings.auto_index_repositories
        items = [
            Repository(
                provider=command.provider,
                external_repo_id=command.external_repo_id,
                owner=command.owner,
                name=command.name,
                clone_url=command.clone_url,
                default_branch=command.default_branch,
                index_status=(
                    IndexStatus.QUEUED
                    if prepare_knowledge and auto_index
                    else IndexStatus.NOT_INDEXED
                ),
                index_error=None,
            )
            for command in commands
        ]
        self._session.add_all(items)
        await self._session.commit()
        return await self._views(items)

    async def _locked(self, repository_id: uuid.UUID) -> Repository:
        item = await self._session.get(Repository, repository_id, with_for_update=True)
        if item is None:
            raise ManagedRepositoryNotFound("Repository not found")
        return item

    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView:
        item = await self._locked(repository_id)
        if item.archived_at is not None and enabled:
            raise ManagedRepositoryConflict("Restore the repository before enabling it")
        item.enabled = enabled
        if enabled:
            item.index_status, item.index_error = IndexStatus.QUEUED, None
        await self._session.commit()
        return (await self._views([item]))[0]

    async def set_archived(self, repository_id: uuid.UUID, archived: bool) -> RepositoryView:
        item = await self._locked(repository_id)
        item.archived_at = datetime.now(UTC) if archived else None
        item.enabled = not archived
        if not archived:
            item.index_status, item.index_error = IndexStatus.QUEUED, None
        await self._session.commit()
        return (await self._views([item]))[0]

    async def queue_index(self, repository_id: uuid.UUID) -> RepositoryView:
        item = await self._locked(repository_id)
        if not item.enabled or item.archived_at is not None:
            raise ManagedRepositoryConflict("Repository is disabled or archived")
        item.index_status, item.index_error = IndexStatus.QUEUED, None
        await self._session.commit()
        return (await self._views([item]))[0]

    async def dependencies(self, repository_id: uuid.UUID) -> RepositoryDependencies:
        item = await self._locked(repository_id)
        _, task_context, teams = await self._context([item.id])
        active_tasks, active_workspaces, _ = task_context.get(item.id, (0, 0, None))
        team_names = tuple(
            team.name for team in teams if str(item.id) in (team.repository_ids or [])
        )
        integrations = list((await self._session.scalars(select(Integration))).all())
        task_sources = tuple(
            integration.provider_name
            for integration in integrations
            if str((integration.configuration or {}).get("repository_id") or "") == str(item.id)
        )
        return RepositoryDependencies(team_names, active_tasks, active_workspaces, task_sources)

    async def delete(self, repository_id: uuid.UUID) -> None:
        item = await self._locked(repository_id)
        dependencies = await self.dependencies(repository_id)
        if (
            dependencies.teams
            or dependencies.active_tasks
            or dependencies.active_workspaces
            or dependencies.task_sources
        ):
            raise ManagedRepositoryConflict(
                "Archive this repository or remove its Team, Task, workspace, and task-source dependencies first"
            )
        await self._session.delete(item)
        await self._session.commit()
