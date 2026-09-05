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
class RepositoryView:
    id: uuid.UUID
    provider: str
    external_repo_id: str
    owner: str
    name: str
    clone_url: str
    default_branch: str
    enabled: bool
    local_path: str | None
    latest_sha: str | None
    indexed_sha: str | None
    indexed_at: datetime | None
    index_status: str
    index_error: str | None
    updated_at: datetime
    clone_status: str
    chunk_count: int


class RepositoryManagementWorkflow(Protocol):
    async def list(self) -> list[RepositoryView]: ...
    async def create(self, command: CreateRepositoryCommand) -> RepositoryView: ...
    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView: ...
    async def queue_index(self, repository_id: uuid.UUID) -> RepositoryView: ...
