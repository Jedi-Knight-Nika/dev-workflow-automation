import builtins
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class ManagedRepositoryNotFound(Exception):
    pass


class ManagedRepositoryConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreateRepositoryCommand:
    provider: str
    external_repo_id: str
    owner: str
    name: str
    clone_url: str
    default_branch: str


@dataclass(frozen=True, slots=True)
class RepositoryDependencies:
    teams: tuple[str, ...] = ()
    active_tasks: int = 0
    active_workspaces: int = 0
    task_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryView:
    id: uuid.UUID
    provider: str
    external_repo_id: str
    owner: str
    name: str
    clone_url: str
    default_branch: str
    enabled: bool
    latest_sha: str | None
    updated_at: datetime
    archived_at: datetime | None = None
    teams_count: int = 0
    active_tasks_count: int = 0
    active_workspaces_count: int = 0
    last_activity_at: datetime | None = None


class RepositoryManagementWorkflow(Protocol):
    async def list(self, include_archived: bool = False) -> builtins.list[RepositoryView]: ...

    async def create(self, command: CreateRepositoryCommand) -> RepositoryView: ...

    async def import_batch(
        self, commands: builtins.list[CreateRepositoryCommand]
    ) -> builtins.list[RepositoryView]: ...

    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView: ...

    async def set_archived(self, repository_id: uuid.UUID, archived: bool) -> RepositoryView: ...

    async def dependencies(self, repository_id: uuid.UUID) -> RepositoryDependencies: ...

    async def delete(self, repository_id: uuid.UUID) -> None: ...
