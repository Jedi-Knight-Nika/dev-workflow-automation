from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.infrastructure.models import (
    AIRun,
    DeveloperSession,
    DeveloperTokenPolicy,
    PricingCatalog,
)
from app.agent_runtime.infrastructure.receipts import apply_receipt, known_no_inference
from app.agent_runtime.infrastructure.reservations import reserve_budget
from app.agent_runtime.infrastructure.token_efficiency import ensure_generation
from app.engineering.application.develop import checkpoint_payload
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState


class SqlDevelopmentStore:
    """Short transactions around a native turn, never a DB lock during inference.

    The scheduler supplies the session and job lease. It must heartbeat that
    lease and interrupt the container when revoked. Receipts are retained even
    if the task is paused after inference, but cannot authorize further work.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        session_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        pricing_id: UUID | None = None,
        reservation_usd: Decimal | None = None,
        operation: str = "development",
    ) -> None:
        self.sessions = sessions
        self.session_id, self.job_id = session_id, job_id
        self.lease_token, self.pricing_id = lease_token, pricing_id
        self.reservation_usd = reservation_usd
        self.operation = operation

    async def progress(self, snapshot: dict[str, Any]) -> None:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(AIRun)
                .where(
                    AIRun.job_id == self.job_id,
                    AIRun.session_id == self.session_id,
                    AIRun.status == "RUNNING",
                )
                .with_for_update()
            )
            if row:
                row.token_efficiency = snapshot
                # Operational signal only. Provider receipts own all invoice fields.
                row.active_context_estimate = snapshot.get("active_context_estimate")
                row.active_context_estimate_source = "last-inference-input-estimate"

    async def _assert_runnable(self, session: AsyncSession, task_id: UUID) -> None:
        job = await session.get(Job, self.job_id)
        task = await session.get(Task, task_id)
        native = await session.get(DeveloperSession, self.session_id)
        now = datetime.now(UTC)
        if (
            job is None
            or task is None
            or native is None
            or job.task_id != task_id
            or native.task_id != task_id
            or native.state == "SUPERSEDED"
            or job.lease_token != self.lease_token
            or job.state != JobState.RUNNING
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
            or task.status != "ACTIVE"
            or task.stage not in {"DEVELOPING", "FIXING"}
            or task.manual_takeover
        ):
            raise ValueError("Development lease is no longer runnable")

    async def assert_runnable(self, task_id: UUID) -> None:
        async with self.sessions() as session:
            await self._assert_runnable(session, task_id)

    async def consumed_cost(self, task_id: UUID) -> Decimal | None:
        async with self.sessions() as session:
            rows = await session.scalars(select(AIRun).where(AIRun.task_id == task_id))
            total = Decimal(0)
            for row in rows:
                cost = (
                    row.provider_cost_usd
                    if row.provider_cost_usd is not None
                    else row.calculated_cost_usd
                )
                if cost is None or row.status == "RUNNING":
                    return None
                total += cost
            return total

    async def session_started(self, task_id: UUID, native_id: str) -> None:
        async with self.sessions.begin() as session:
            await self._assert_runnable(session, task_id)
            row = await session.get(DeveloperSession, self.session_id, with_for_update=True)
            assert row is not None
            if row.native_session_id and row.native_session_id != native_id:
                raise ValueError("Cannot replace an existing native session implicitly")
            row.native_session_id = native_id
            generation = await ensure_generation(session, row, {})
            generation.native_thread_id = native_id

    async def begin_run(self, task_id: UUID, requirement_version: int) -> UUID:
        async with self.sessions.begin() as session:
            await self._assert_runnable(session, task_id)
            if self.reservation_usd is not None:
                await reserve_budget(session, task_id, self.reservation_usd)
            task = await session.get(Task, task_id, with_for_update=True)
            native = await session.get(DeveloperSession, self.session_id, with_for_update=True)
            assert task is not None and native is not None
            if task.requirement_version != requirement_version:
                raise ValueError("Requirements changed before the turn began")
            if native.state == "RUNNING":
                raise ValueError("Another turn already owns this session")
            if await session.scalar(
                select(AIRun.id).where(AIRun.task_id == task_id, AIRun.status == "RUNNING").limit(1)
            ):
                raise ValueError("Another run already owns this task")
            native.state = "RUNNING"
            native.requirement_version = requirement_version
            policy = await session.get(DeveloperTokenPolicy, task.team_id) if task.team_id else None
            generation = await ensure_generation(
                session,
                native,
                native.checkpoint.get("token_policy_override") or (policy.values if policy else {}),
            )
            row = AIRun(
                task_id=task_id,
                session_id=native.id,
                job_id=self.job_id,
                role_kind="DEVELOPER",
                requirement_version=requirement_version,
                provider=native.provider,
                model=native.model,
                harness=native.harness,
                prompt_version="v2.compaction.1" if self.operation == "compaction" else "v2.1",
                status="RUNNING",
                reserved_cost_usd=self.reservation_usd,
                pricing_id=self.pricing_id,
                context_generation_id=generation.id,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def finish_run(self, run_id: UUID, receipt: TurnReceipt) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AIRun, run_id, with_for_update=True)
            if row is None or row.session_id != self.session_id or row.job_id != self.job_id:
                raise ValueError("Receipt does not belong to this execution")
            late_receipt = (
                row.status == "INTERRUPTED"
                and row.failure_code in {"ORPHAN_STOPPED", "EXPIRED_LEASE"}
                and row.native_turn_id is None
                and row.provider_cost_usd is None
                and row.calculated_cost_usd is None
            )
            if row.status != "RUNNING" and not late_receipt:
                if row.native_turn_id == receipt.native_turn_id:
                    return
                raise ValueError("Run already finished")
            native = await session.get(DeveloperSession, self.session_id, with_for_update=True)
            assert native is not None
            if native.native_session_id != receipt.native_session_id:
                raise ValueError("Receipt belongs to a different native session")
            price = await session.get(PricingCatalog, self.pricing_id) if self.pricing_id else None
            apply_receipt(row, receipt, price)
            row.token_efficiency = receipt.token_efficiency or None
            row.active_context_estimate = receipt.token_efficiency.get("active_context_estimate")
            row.active_context_estimate_source = (
                receipt.token_efficiency.get("measurement_quality") or {}
            ).get("active_context")
            if late_receipt:
                # Accept genuine billing that raced orphan recovery. This does
                # not revive work, consume feedback, or change task/phase state.
                native.state = "BLOCKED"
                if receipt.cumulative_usage is not None:
                    native.checkpoint = {
                        **native.checkpoint,
                        "cumulative_usage": receipt.cumulative_usage,
                    }
                return
            native.state = "READY" if receipt.status == "completed" else "BLOCKED"
            checkpoint = {
                **native.checkpoint,
                **checkpoint_payload(receipt, native.requirement_version),
            }
            checkpoint["token_efficiency"] = receipt.token_efficiency
            if self.operation == "continuity":
                digest = native.checkpoint.get("rollover_digest")
                checkpoint["summary"] = native.checkpoint.get("summary", "")
                if (
                    receipt.status == "completed"
                    and digest
                    and receipt.summary.strip() == "ACK " + digest
                ):
                    checkpoint["continuity_acknowledged"] = digest
                    checkpoint["continuation_pending"] = True
                else:
                    native.state = "BLOCKED"
            elif self.operation == "development" and receipt.status == "completed":
                checkpoint["continuation_pending"] = False
            if self.operation == "compaction":
                assert row.finished_at is not None
                checkpoint["summary"] = native.checkpoint.get("summary", "")
                checkpoint["compaction_count"] = (
                    int(native.checkpoint.get("compaction_count", 0)) + 1
                )
                checkpoint["last_compaction_at"] = row.finished_at.isoformat()
                checkpoint["compacted_input_tokens"] = (receipt.cumulative_usage or {}).get(
                    "input_tokens", 0
                )
            native.checkpoint = checkpoint
            task = await session.get(Task, row.task_id)
            # A tracker edit can revoke this turn while its final receipt is in
            # flight. Account the receipt, but do not consume the newer delta.
            if (
                self.operation == "development"
                and task
                and task.requirement_version == native.requirement_version
            ):
                native.checkpoint.pop("next_feedback", None)

    async def fail_run(self, run_id: UUID, code: str, *, inference_started: bool = True) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(AIRun, run_id, with_for_update=True)
            if row is None or row.job_id != self.job_id or row.session_id != self.session_id:
                raise ValueError("Unknown run")
            if row.status == "RUNNING":
                row.status, row.failure_code = "FAILED", code[:100]
                row.finished_at = datetime.now(UTC)
                if not inference_started:
                    # The controller never authorized run_turn. This is known non-usage,
                    # unlike a lost receipt after a paid request was sent.
                    known_no_inference(row)
                # Unknown provider usage is intentionally not overwritten with 0.
                native = await session.get(DeveloperSession, self.session_id, with_for_update=True)
                if native:
                    native.state = "BLOCKED"
