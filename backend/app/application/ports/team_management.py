import builtins
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class TeamNotFound(Exception):
    pass


class TeamConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SaveTeamCommand:
    name: str
    description: str = ""
    enabled: bool = True
    max_concurrent_tasks: int = 1
    repository_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class AssignTaskCommand:
    task_id: uuid.UUID
    team_id: uuid.UUID
    reason: str = "manual"


@dataclass(frozen=True, slots=True)
class TeamView:
    id: uuid.UUID
    name: str
    description: str
    enabled: bool
    max_concurrent_tasks: int
    repository_ids: tuple[uuid.UUID, ...]
    queued_tasks: int
    running_tasks: int
    completed_tasks: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TaskAssignmentView:
    id: uuid.UUID
    task_id: uuid.UUID
    team_id: uuid.UUID
    status: str
    queue_position: int
    reason: str
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class WakeTeamResult:
    recovered_jobs: int
    created_jobs: int
    queued_jobs: int
    running_jobs: int
    missing_repository_tasks: int


class TeamManagementWorkflow(Protocol):
    async def list(self) -> list[TeamView]: ...
    async def get(self, team_id: uuid.UUID) -> TeamView | None: ...
    async def create(self, command: SaveTeamCommand) -> TeamView: ...
    async def update(self, team_id: uuid.UUID, command: SaveTeamCommand) -> TeamView: ...
    async def archive(self, team_id: uuid.UUID) -> None: ...
    async def assign(self, command: AssignTaskCommand) -> TaskAssignmentView: ...
    async def unassign(self, task_id: uuid.UUID) -> None: ...
    async def assignments(self, team_id: uuid.UUID) -> builtins.list[TaskAssignmentView]: ...
    async def wake(self, team_id: uuid.UUID) -> WakeTeamResult: ...
