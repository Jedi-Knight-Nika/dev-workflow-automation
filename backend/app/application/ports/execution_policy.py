import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.security import TeamExecutionPolicy


@dataclass(frozen=True, slots=True)
class ApprovalView:
    id: uuid.UUID
    team_id: uuid.UUID
    task_id: uuid.UUID
    job_id: uuid.UUID
    agent_id: uuid.UUID | None
    tool: str
    action: str
    arguments: dict[str, object]
    reason: str
    state: str
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class ToolEventView:
    id: uuid.UUID
    team_id: uuid.UUID
    task_id: uuid.UUID
    job_id: uuid.UUID
    tool: str
    action: str
    decision: str
    policy_rule: str
    arguments: dict[str, object]
    exit_code: int | None
    duration_ms: int | None
    created_at: datetime


class ExecutionPolicyStore(Protocol):
    async def get_policy(self, team_id: uuid.UUID) -> TeamExecutionPolicy: ...
    async def save_policy(
        self, team_id: uuid.UUID, policy: TeamExecutionPolicy
    ) -> TeamExecutionPolicy: ...
    async def approvals(self, state: str | None = None) -> list[ApprovalView]: ...
    async def resolve_approval(
        self, approval_id: uuid.UUID, approved: bool, resolved_by: str, scope: str
    ) -> ApprovalView: ...
    async def tool_events(
        self, *, task_id: uuid.UUID | None = None, job_id: uuid.UUID | None = None
    ) -> list[ToolEventView]: ...
