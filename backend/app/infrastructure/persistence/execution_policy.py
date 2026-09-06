import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.execution_policy import ApprovalView, ToolEventView
from app.db.models import (
    AccountSettings,
    ApprovalRequest,
    ExecutionPolicy,
    Team,
    ToolExecutionEvent,
)
from app.domain.security import Decision, ExecutionMode, TeamExecutionPolicy


class SqlAlchemyExecutionPolicyStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_policy(self, team_id: uuid.UUID) -> TeamExecutionPolicy:
        if await self._session.get(Team, team_id) is None:
            raise LookupError("Team not found")
        record = await self._session.scalar(
            select(ExecutionPolicy).where(ExecutionPolicy.team_id == team_id)
        )
        if record is None:
            account = await self._session.get(AccountSettings, "default")
            if account is None:
                return TeamExecutionPolicy()
            return TeamExecutionPolicy(
                ExecutionMode(account.default_execution_mode),
                {
                    "INSTALL_DEPENDENCIES": Decision(account.default_dependency_install_policy),
                    "PUSH_TASK_BRANCH": Decision(account.default_push_task_branch_policy),
                    "MERGE_PR": Decision(account.default_merge_policy),
                },
                (),
                min(account.default_job_timeout_seconds, 7200),
                1_000_000,
            )
        return self._domain(record)

    async def save_policy(
        self, team_id: uuid.UUID, policy: TeamExecutionPolicy
    ) -> TeamExecutionPolicy:
        if await self._session.get(Team, team_id) is None:
            raise LookupError("Team not found")
        record = await self._session.scalar(
            select(ExecutionPolicy).where(ExecutionPolicy.team_id == team_id)
        )
        if record is None:
            record = ExecutionPolicy(team_id=team_id)
            self._session.add(record)
        record.mode = policy.mode.value
        record.settings = {key: value.value for key, value in policy.settings.items()}
        record.approved_hosts = list(policy.approved_hosts)
        record.max_command_timeout_seconds = policy.max_command_timeout_seconds
        record.max_output_bytes = policy.max_output_bytes
        await self._session.commit()
        return self._domain(record)

    async def approvals(self, state: str | None = None) -> list[ApprovalView]:
        statement = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        if state:
            statement = statement.where(ApprovalRequest.state == state)
        records = list((await self._session.scalars(statement.limit(200))).all())
        now = datetime.now(UTC)
        changed = False
        for record in records:
            if record.state == "PENDING" and record.expires_at <= now:
                record.state = "EXPIRED"
                changed = True
        if changed:
            await self._session.commit()
        return [self._approval(record) for record in records if not state or record.state == state]

    async def resolve_approval(
        self, approval_id: uuid.UUID, approved: bool, resolved_by: str, scope: str
    ) -> ApprovalView:
        record = await self._session.get(ApprovalRequest, approval_id, with_for_update=True)
        if record is None:
            raise LookupError("Approval request not found")
        if record.state != "PENDING" or record.expires_at <= datetime.now(UTC):
            raise ValueError("Approval request is no longer pending")
        if scope not in {"ONCE", "TASK"}:
            raise ValueError("Approval scope must be ONCE or TASK")
        record.state = "APPROVED" if approved else "DENIED"
        record.resolution_scope = scope
        record.resolved_by = resolved_by[:255]
        record.resolved_at = datetime.now(UTC)
        await self._session.commit()
        return self._approval(record)

    async def tool_events(
        self, *, task_id: uuid.UUID | None = None, job_id: uuid.UUID | None = None
    ) -> list[ToolEventView]:
        statement = (
            select(ToolExecutionEvent).order_by(ToolExecutionEvent.created_at.desc()).limit(500)
        )
        if task_id:
            statement = statement.where(ToolExecutionEvent.task_id == task_id)
        if job_id:
            statement = statement.where(ToolExecutionEvent.job_id == job_id)
        records = list((await self._session.scalars(statement)).all())
        return [
            ToolEventView(
                record.id,
                record.team_id,
                record.task_id,
                record.job_id,
                record.tool,
                record.action,
                record.decision,
                record.policy_rule,
                record.arguments_sanitized or {},
                record.exit_code,
                record.duration_ms,
                record.created_at,
            )
            for record in records
        ]

    @staticmethod
    def _domain(record: ExecutionPolicy) -> TeamExecutionPolicy:
        return TeamExecutionPolicy(
            ExecutionMode(record.mode),
            {key: Decision(value) for key, value in (record.settings or {}).items()},
            tuple(record.approved_hosts or []),
            record.max_command_timeout_seconds,
            record.max_output_bytes,
        )

    @staticmethod
    def _approval(record: ApprovalRequest) -> ApprovalView:
        return ApprovalView(
            record.id,
            record.team_id,
            record.task_id,
            record.job_id,
            record.agent_id,
            record.tool,
            record.action,
            record.arguments or {},
            record.reason,
            record.state,
            record.created_at,
            record.expires_at,
            record.resolved_at,
        )
