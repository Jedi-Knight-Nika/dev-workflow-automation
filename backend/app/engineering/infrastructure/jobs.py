from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.engineering.application.jobs import PhaseLease
from app.engineering.domain.lifecycle import Action, Stage, TaskStatus, WaitReason
from app.engineering.infrastructure.job_queue import claim_next_job
from app.engineering.infrastructure.lifecycle import record_transition, state_of
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.team_models import Team

PHASE_ACTIONS = {
    Stage.INTAKE: "INTERPRET_EVENT",
    Stage.PLANNING: "THINKER_TURN",
    Stage.DEVELOPING: "DEVELOPER_TURN",
    Stage.FIXING: "DEVELOPER_TURN",
    Stage.VALIDATING: "RUN_VALIDATION",
    Stage.PUBLISHING: "PUBLISH_PR",
    Stage.MERGING: "MERGE_PR",
}


async def enqueue_phase(session: AsyncSession, task: Task) -> Job | None:
    """Caller holds the Task lock; insertion and phase change share a transaction."""
    state = state_of(task)
    if state.status not in {TaskStatus.NEW, TaskStatus.ACTIVE}:
        return None
    action = PHASE_ACTIONS.get(state.stage)
    if action is None:
        return None
    existing = await session.scalar(
        select(Job).where(
            Job.task_id == task.id,
            Job.state.in_([JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING]),
        )
    )
    if existing is not None:
        return existing
    job = Job(
        task_id=task.id,
        action=action,
        priority=task.priority,
        payload={"lifecycle_version": task.lifecycle_version},
    )
    session.add(job)
    await session.flush()
    session.add(
        TaskEvent(
            task_id=task.id,
            source="engineering",
            event_type="JOB_QUEUED",
            payload={
                "job_id": str(job.id),
                "action": action,
                "lifecycle_version": task.lifecycle_version,
            },
        )
    )
    return job


class SqlPhaseJobs:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        worker_id: str,
        lease_seconds: int,
        *,
        orphan_cleanup: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.sessions, self.worker_id, self.lease_seconds = sessions, worker_id, lease_seconds
        self.orphan_cleanup = orphan_cleanup

    async def claim(self) -> PhaseLease | None:
        async with self.sessions() as session:
            job = await claim_next_job(session, self.worker_id, self.lease_seconds)
            if job is None:
                return None
            assert job.lease_token is not None
            lease = PhaseLease(
                job.id,
                job.task_id,
                job.lease_token,
                job.action,
                int(job.payload.get("lifecycle_version", 0)),
            )
        # The claimed row is persisted before any native process is created.
        if not await self.heartbeat(lease):
            await self.block(
                lease,
                WaitReason.MISSING_CONFIGURATION,
                "Stale phase job; task changed before execution",
            )
            return None
        return lease

    async def _locked(self, session: AsyncSession, lease: PhaseLease) -> tuple[Task, Job] | None:
        task = await session.get(Task, lease.task_id, with_for_update=True)
        job = await session.get(Job, lease.job_id, with_for_update=True)
        if (
            task is None
            or job is None
            or job.task_id != task.id
            or job.lease_token != lease.token
            or job.state not in {JobState.CLAIMED, JobState.RUNNING}
        ):
            return None
        return task, job

    async def heartbeat(self, lease: PhaseLease) -> bool:
        async with self.sessions.begin() as session:
            pair = await self._locked(session, lease)
            if pair is None:
                return False
            task, job = pair
            team = await session.get(Team, task.team_id) if task.team_id else None
            now = datetime.now(UTC)
            if (
                task.lifecycle_version != lease.lifecycle_version
                or task.status not in {"NEW", "ACTIVE"}
                or task.manual_takeover
                or task.archived_at is not None
                or team is None
                or not team.enabled
                or team.execution_paused
                or team.archived_at is not None
                or job.lease_expires_at is None
                or job.lease_expires_at <= now
                or PHASE_ACTIONS.get(Stage(task.stage or "INTAKE")) != lease.action
            ):
                return False
            job.state = JobState.RUNNING
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            return True

    async def complete(self, lease: PhaseLease, action: Action) -> None:
        async with self.sessions.begin() as session:
            pair = await self._locked(session, lease)
            if pair is None:
                return
            task, job = pair
            if (
                task.lifecycle_version != lease.lifecycle_version
                or task.status not in {"NEW", "ACTIVE"}
                or task.manual_takeover
                or job.lease_expires_at is None
                or job.lease_expires_at <= datetime.now(UTC)
            ):
                return
            # Validate which step is allowed to advance; a model cannot return MERGED.
            allowed = {
                "INTERPRET_EVENT": {Action.START},
                "DEVELOPER_TURN": {Action.IMPLEMENTED, Action.NEEDS_PLAN},
                "THINKER_TURN": {Action.PLAN_READY},
                "RUN_VALIDATION": {Action.VALIDATION_PASSED, Action.VALIDATION_FAILED},
                "PUBLISH_PR": {Action.PUBLISHED},
                "MERGE_PR": {Action.MERGED, Action.MERGE_RECHECK},
            }
            if action not in allowed.get(lease.action, set()):
                raise ValueError("Phase result does not match its execution unit")
            await record_transition(
                session,
                task.id,
                action,
                expected_version=lease.lifecycle_version,
                actor=self.worker_id,
            )
            job.state, job.finished_at = JobState.SUCCEEDED, datetime.now(UTC)
            job.result = {"action": action.value, "lifecycle_version": task.lifecycle_version}
            job.lease_token, job.lease_expires_at = None, None
            await session.flush()
            if action == Action.PUBLISHED:
                from app.intake.infrastructure.engineering_events import apply_pending_feedback

                queued = await session.scalars(
                    select(ReviewCycle).where(
                        ReviewCycle.task_id == task.id,
                        ReviewCycle.decision == "CLASSIFY_AFTER_PHASE",
                    )
                )
                for row in queued:
                    row.decision = (
                        "CLASSIFY_PENDING" if row.head_sha == task.current_revision else "STALE"
                    )
                await apply_pending_feedback(session, task)
            await enqueue_phase(session, task)

    async def block(self, lease: PhaseLease, reason: WaitReason, message: str) -> None:
        async with self.sessions.begin() as session:
            pair = await self._locked(session, lease)
            if pair is None:
                return
            task, job = pair
            job.state, job.finished_at = JobState.WAITING_HUMAN, datetime.now(UTC)
            job.failure_reason = message[:1000]
            job.lease_token, job.lease_expires_at = None, None
            if task.lifecycle_version == lease.lifecycle_version and task.status in {
                "NEW",
                "ACTIVE",
            }:
                await record_transition(
                    session,
                    task.id,
                    Action.BLOCK,
                    expected_version=lease.lifecycle_version,
                    actor=self.worker_id,
                    wait_reason=reason,
                )

    async def recover(self) -> None:
        if self.orphan_cleanup:
            await self.orphan_cleanup()
        # Never rerun a lost native turn without reconciling its cost and container.
        async with self.sessions() as session:
            jobs = list(
                await session.scalars(
                    select(Job)
                    .join(Task)
                    .where(
                        Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
                        Job.lease_expires_at < datetime.now(UTC),
                    )
                )
            )
            leases = [
                PhaseLease(
                    j.id,
                    j.task_id,
                    j.lease_token,
                    j.action,
                    int(j.payload.get("lifecycle_version", 0)),
                )
                for j in jobs
                if j.lease_token
            ]
        for lease in leases:
            await self.block(
                lease,
                WaitReason.MISSING_CONFIGURATION,
                "Expired runner lease; preserve workspace and reconcile usage before retry",
            )
            async with self.sessions.begin() as session:
                runs = await session.scalars(
                    select(AIRun)
                    .where(AIRun.job_id == lease.job_id, AIRun.status == "RUNNING")
                    .with_for_update()
                )
                for run in runs:
                    run.status, run.failure_code, run.finished_at = (
                        "INTERRUPTED",
                        "EXPIRED_LEASE",
                        datetime.now(UTC),
                    )
                    native = (
                        await session.get(DeveloperSession, run.session_id)
                        if run.session_id
                        else None
                    )
                    if native:
                        native.state = "BLOCKED"
