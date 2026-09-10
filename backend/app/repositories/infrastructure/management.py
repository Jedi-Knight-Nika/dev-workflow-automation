import builtins
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.engineering.domain.lifecycle import TaskStatus
from app.engineering.infrastructure.task_models import Task
from app.platform.integrations.models import Integration
from app.repositories.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
    ManagedRepositoryNotFound,
    RepositoryDependencies,
    RepositoryView,
)
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.team_models import Team

TERMINAL_TASK_STATES = {TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.MERGED}


class SqlAlchemyRepositoryManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _context(
        self, repository_ids: builtins.list[uuid.UUID]
    ) -> tuple[
        dict[uuid.UUID, tuple[int, int, datetime | None]],
        builtins.list[Team],
    ]:
        if not repository_ids:
            return {}, []
        task_rows = (
            await self._session.execute(
                select(
                    Task.repository_id,
                    func.count(Task.id)
                    .filter(Task.status.not_in(TERMINAL_TASK_STATES))
                    .label("active_tasks"),
                    func.count(Task.id)
                    .filter(
                        Task.status.not_in(TERMINAL_TASK_STATES),
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
        return tasks, teams

    def _view(
        self,
        item: Repository,
        tasks: dict[uuid.UUID, tuple[int, int, datetime | None]],
        teams: builtins.list[Team],
    ) -> RepositoryView:
        active_tasks, active_workspaces, last_activity = tasks.get(item.id, (0, 0, None))
        return RepositoryView(
            id=item.id,
            provider=item.provider,
            external_repo_id=item.external_repo_id,
            owner=item.owner,
            name=item.name,
            clone_url=item.clone_url,
            default_branch=item.default_branch,
            enabled=item.enabled,
            latest_sha=item.latest_sha,
            updated_at=item.updated_at,
            archived_at=item.archived_at,
            teams_count=sum(str(item.id) in (team.repository_ids or []) for team in teams),
            active_tasks_count=active_tasks,
            active_workspaces_count=active_workspaces,
            last_activity_at=last_activity or item.updated_at,
        )

    async def _views(self, items: builtins.list[Repository]) -> builtins.list[RepositoryView]:
        tasks, teams = await self._context([item.id for item in items])
        return [self._view(item, tasks, teams) for item in items]

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
        return (await self.import_batch([command]))[0]

    async def import_batch(
        self, commands: builtins.list[CreateRepositoryCommand]
    ) -> builtins.list[RepositoryView]:
        if not commands:
            return []
        keys = {(command.provider, command.external_repo_id) for command in commands}
        if len(keys) != len(commands):
            raise ManagedRepositoryConflict("Repository selection contains duplicates")
        existing = await self._session.scalar(
            select(
                select(Repository.id)
                .where(tuple_(Repository.provider, Repository.external_repo_id).in_(keys))
                .exists()
            )
        )
        if existing:
            raise ManagedRepositoryConflict("One or more repositories are already imported")
        items = [
            Repository(
                provider=command.provider,
                external_repo_id=command.external_repo_id,
                owner=command.owner,
                name=command.name,
                clone_url=command.clone_url,
                default_branch=command.default_branch,
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
        await self._session.commit()
        return (await self._views([item]))[0]

    async def set_archived(self, repository_id: uuid.UUID, archived: bool) -> RepositoryView:
        item = await self._locked(repository_id)
        item.archived_at = datetime.now(UTC) if archived else None
        item.enabled = not archived
        await self._session.commit()
        return (await self._views([item]))[0]

    async def dependencies(self, repository_id: uuid.UUID) -> RepositoryDependencies:
        item = await self._locked(repository_id)
        return await self._dependencies(item)

    async def _dependencies(self, item: Repository) -> RepositoryDependencies:
        task_context, teams = await self._context([item.id])
        active_tasks, active_workspaces, _ = task_context.get(item.id, (0, 0, None))
        team_names = tuple(
            team.name for team in teams if str(item.id) in (team.repository_ids or [])
        )
        integrations = (
            await self._session.scalars(
                select(Integration).options(
                    load_only(Integration.provider_name, Integration.configuration, raiseload=True)
                )
            )
        ).all()
        task_sources = tuple(
            integration.provider_name
            for integration in integrations
            if str((integration.configuration or {}).get("repository_id") or "") == str(item.id)
        )
        return RepositoryDependencies(team_names, active_tasks, active_workspaces, task_sources)

    async def delete(self, repository_id: uuid.UUID) -> None:
        item = await self._locked(repository_id)
        dependencies = await self._dependencies(item)
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
