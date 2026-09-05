import uuid

from app.application.ports.execution_policy import ApprovalView, ExecutionPolicyStore, ToolEventView
from app.domain.security import TeamExecutionPolicy


class ManageExecutionPolicy:
    def __init__(self, store: ExecutionPolicyStore) -> None:
        self._store = store

    async def get(self, team_id: uuid.UUID) -> TeamExecutionPolicy:
        return await self._store.get_policy(team_id)

    async def save(self, team_id: uuid.UUID, policy: TeamExecutionPolicy) -> TeamExecutionPolicy:
        return await self._store.save_policy(team_id, policy)

    async def approvals(self, state: str | None = None) -> list[ApprovalView]:
        return await self._store.approvals(state)

    async def resolve(
        self, approval_id: uuid.UUID, approved: bool, resolved_by: str, scope: str
    ) -> ApprovalView:
        return await self._store.resolve_approval(approval_id, approved, resolved_by, scope)

    async def tool_events(
        self, *, task_id: uuid.UUID | None = None, job_id: uuid.UUID | None = None
    ) -> list[ToolEventView]:
        return await self._store.tool_events(task_id=task_id, job_id=job_id)
