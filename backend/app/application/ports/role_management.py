import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class RoleNotFound(Exception):
    pass


class RoleConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SaveRoleCommand:
    name: str
    category: str
    description: str
    system_instructions: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    allowed_results: tuple[str, ...]
    knowledge_collection_ids: tuple[uuid.UUID, ...] = ()
    default_provider: str | None = None
    default_model: str | None = None
    default_reasoning_effort: str = "default"
    default_timeout_minutes: int = 30
    default_max_retries: int = 2
    enabled: bool = True
    runtime_profile: dict[str, Any] | None = None
    override_policy: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class RoleView:
    id: uuid.UUID
    name: str
    category: str
    description: str
    system_instructions: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    allowed_results: tuple[str, ...]
    knowledge_collection_ids: tuple[uuid.UUID, ...]
    default_provider: str | None
    default_model: str | None
    default_reasoning_effort: str
    default_timeout_minutes: int
    default_max_retries: int
    enabled: bool
    built_in: bool
    version: int
    active_agents: int
    inactive_agents: int
    total_agents: int
    created_at: datetime
    updated_at: datetime
    runtime_profile: dict[str, Any] = field(default_factory=dict)
    override_policy: dict[str, str] = field(default_factory=dict)


class RoleManagementWorkflow(Protocol):
    async def list(self) -> list[RoleView]: ...
    async def get(self, role_id: uuid.UUID) -> RoleView | None: ...
    async def create(self, command: SaveRoleCommand, *, built_in: bool = False) -> RoleView: ...
    async def update(self, role_id: uuid.UUID, command: SaveRoleCommand) -> RoleView: ...
    async def clone(self, role_id: uuid.UUID, name: str) -> RoleView: ...
    async def disable(self, role_id: uuid.UUID) -> RoleView: ...
    async def delete(self, role_id: uuid.UUID) -> None: ...
