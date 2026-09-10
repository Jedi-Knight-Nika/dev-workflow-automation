"""A bounded read-only consultation has its own receipt, not a replacement Developer session."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.infrastructure.models import AIRun, PricingCatalog
from app.agent_runtime.infrastructure.receipts import apply_receipt, known_no_inference
from app.agent_runtime.infrastructure.reservations import consumed_cost, reserve_budget
from app.engineering.application.jobs import PhaseLease
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


class SqlHelperStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        lease: PhaseLease,
        profile: TeamAgentProfile,
        reservation: Decimal,
        pricing_id: UUID | None,
    ) -> None:
        self.sessions, self.lease, self.profile = sessions, lease, profile
        self.reservation, self.pricing_id = reservation, pricing_id
        self.run_id: UUID | None = None

    async def _assert(self, session: AsyncSession, task_id: UUID) -> None:
        task, job = await session.get(Task, task_id), await session.get(Job, self.lease.job_id)
        team = await session.get(Team, task.team_id) if task and task.team_id else None
        stage = "PLANNING" if self.profile.role_kind == "THINKER" else "VALIDATING"
        if not (
            task
            and job
            and team
            and team.enabled
            and not team.execution_paused
            and not team.archived_at
            and task.id == self.lease.task_id
            and job.task_id == task.id
            and task.lifecycle_version == self.lease.lifecycle_version
            and task.status == "ACTIVE"
            and not task.manual_takeover
            and not task.archived_at
            and task.stage == stage
            and job.state == JobState.RUNNING
            and job.lease_token == self.lease.token
            and job.lease_expires_at
            and job.lease_expires_at > datetime.now(UTC)
        ):
            raise ValueError("Consultation lease is no longer runnable")

    async def assert_runnable(self, task_id: UUID) -> None:
        async with self.sessions() as session:
            await self._assert(session, task_id)

    async def consumed_cost(self, task_id: UUID) -> Decimal | None:
        async with self.sessions() as session:
            return await consumed_cost(session, task_id)

    async def begin_run(self, task_id: UUID, requirement_version: int) -> UUID:
        async with self.sessions.begin() as session:
            await reserve_budget(
                session,
                task_id,
                self.reservation,
                role_kind=self.profile.role_kind,
                role_budget=self.profile.hard_budget_usd,
            )
            await self._assert(session, task_id)
            task = await session.get(Task, task_id)
            if task is None or task.requirement_version != requirement_version:
                raise ValueError("Requirement changed")
            if await session.scalar(
                select(AIRun.id).where(AIRun.task_id == task_id, AIRun.status == "RUNNING")
            ):
                raise ValueError("Another turn owns the task")
            row = AIRun(
                task_id=task_id,
                job_id=self.lease.job_id,
                role_kind=self.profile.role_kind,
                provider=self.profile.provider,
                model=self.profile.model,
                harness=self.profile.harness,
                prompt_version=self.profile.prompt_version,
                requirement_version=requirement_version,
                reserved_cost_usd=self.reservation,
                pricing_id=self.pricing_id,
            )
            session.add(row)
            await session.flush()
            self.run_id = row.id
            return row.id

    async def session_started(self, task_id: UUID, native_id: str) -> None:
        async with self.sessions.begin() as session:
            await self._assert(session, task_id)
            row = await session.get(AIRun, self.run_id, with_for_update=True)
            if row is None or row.status != "RUNNING":
                raise ValueError("Consultation has no reservation")
            row.native_session_id = native_id

    async def finish_run(self, run_id: UUID, receipt: TurnReceipt) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AIRun, run_id, with_for_update=True)
            if (
                row is None
                or row.job_id != self.lease.job_id
                or row.native_session_id != receipt.native_session_id
            ):
                raise ValueError("Receipt belongs to another consultation")
            if row.native_turn_id == receipt.native_turn_id:
                return
            if row.status not in {"RUNNING", "INTERRUPTED"}:
                raise ValueError("Consultation already finished")
            price = await session.get(PricingCatalog, self.pricing_id) if self.pricing_id else None
            apply_receipt(row, receipt, price)

    async def fail_run(self, run_id: UUID, code: str, *, inference_started: bool = True) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AIRun, run_id, with_for_update=True)
            if row is None or row.job_id != self.lease.job_id:
                raise ValueError("Unknown consultation")
            if row.status == "RUNNING":
                row.status, row.failure_code, row.finished_at = (
                    "FAILED",
                    code[:100],
                    datetime.now(UTC),
                )
                if not inference_started:
                    known_no_inference(row)
