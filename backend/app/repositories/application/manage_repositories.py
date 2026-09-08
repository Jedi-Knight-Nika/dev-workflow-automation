import builtins
import uuid

from app.repositories.application.ports.repository_management import (
    CreateRepositoryCommand,
    RepositoryDependencies,
    RepositoryManagementWorkflow,
    RepositoryView,
)


class ManageRepositories:
    def __init__(self, workflow: RepositoryManagementWorkflow) -> None:
        self._workflow = workflow

    async def list(self, include_archived: bool = False) -> builtins.list[RepositoryView]:
        return await self._workflow.list(include_archived)

    async def create(self, command: CreateRepositoryCommand) -> RepositoryView:
        return await self._workflow.create(command)

    async def import_batch(
        self, commands: builtins.list[CreateRepositoryCommand]
    ) -> builtins.list[RepositoryView]:
        return await self._workflow.import_batch(commands)

    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView:
        return await self._workflow.set_enabled(repository_id, enabled)

    async def set_archived(self, repository_id: uuid.UUID, archived: bool) -> RepositoryView:
        return await self._workflow.set_archived(repository_id, archived)

    async def dependencies(self, repository_id: uuid.UUID) -> RepositoryDependencies:
        return await self._workflow.dependencies(repository_id)

    async def delete(self, repository_id: uuid.UUID) -> None:
        await self._workflow.delete(repository_id)
