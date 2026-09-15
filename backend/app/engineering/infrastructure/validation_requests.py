"""Request deterministic validation of a settled candidate, without declaring success."""

from datetime import UTC, datetime

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.domain.handoffs import validate_result, work_packet
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.agent_runtime.infrastructure.reservations import consumed_cost
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import enqueue_phase
from app.engineering.infrastructure.lifecycle import record_transition
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState


async def request_validation(session: AsyncSession, task: Task, *, actor: str) -> None:
    """Caller holds the task lock and has verified Team/repository/operator authority."""
    if task.status != "ACTIVE" or task.stage not in {"DEVELOPING", "FIXING", "VALIDATING"}:
        raise ValueError("Validation requires an active candidate in development or validation")
    jobs = list(
        await session.scalars(
            select(Job)
            .where(
                Job.task_id == task.id,
                Job.state.in_(
                    [JobState.QUEUED, JobState.RETRY_WAIT, JobState.CLAIMED, JobState.RUNNING]
                ),
            )
            .with_for_update()
        )
    )
    if any(job.state in {JobState.CLAIMED, JobState.RUNNING} for job in jobs):
        raise ValueError("Wait for the current engineering worker before requesting validation")
    native = await session.scalar(
        select(DeveloperSession)
        .where(
            DeveloperSession.task_id == task.id,
        )
        .order_by(DeveloperSession.generation.desc())
        .limit(1)
        .with_for_update()
    )
    if (
        not native
        or native.state == "RUNNING"
        or native.requirement_version != task.requirement_version
    ):
        raise ValueError("Validation requires a settled session for the current requirement")
    if await consumed_cost(session, task.id) is None:
        raise ValueError("Reconcile unknown usage before validating")
    prior = await session.scalar(
        select(AIRun)
        .where(
            AIRun.session_id == native.id,
            AIRun.role_kind == "DEVELOPER",
            AIRun.requirement_version == task.requirement_version,
        )
        .order_by(AIRun.started_at.desc())
        .limit(1)
    )
    if not prior or prior.status != "COMPLETED":
        raise ValueError("There is no settled Developer candidate to validate")
    # The latest receipt owns completion. A checkpoint can retain an older success
    # across a failed/partial turn, compaction, or a new native context.
    recorded = (prior.raw_usage or {}).get("agent_result")
    outcome: str
    if recorded is not None:
        result = TypeAdapter(AgentEnvelope).validate_python(recorded)
        outcome = validate_result(
            result,
            work_packet(task.id, task.requirement_version, task.current_revision, task.title),
        )
        if result.payload["turn_id"] != prior.native_turn_id:
            raise ValueError("Validation result does not belong to the latest receipt")
    else:
        outcome = (prior.artifact or "").strip().split("\n", 1)[0]
    if outcome != "IMPLEMENTED":
        raise ValueError("There is no completed Developer candidate to validate")
    # The existing validator inspects the current workspace under its own lock,
    # executes only repository-configured commands, and supplies pass/fail evidence.
    for job in jobs:
        job.state, job.finished_at = JobState.CANCELLED, datetime.now(UTC)
    if task.stage != "VALIDATING":
        await record_transition(
            session,
            task.id,
            Action.VALIDATE_CANDIDATE,
            expected_version=task.lifecycle_version,
            actor=actor,
        )
    await session.flush()
    await enqueue_phase(session, task)
