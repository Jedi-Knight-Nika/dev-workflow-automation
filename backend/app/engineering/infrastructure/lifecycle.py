from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.infrastructure.status_sync import enqueue_status
from app.engineering.domain.lifecycle import (
    Action,
    EngineeringState,
    Stage,
    TaskStatus,
    WaitReason,
    transition,
)
from app.engineering.infrastructure.models import TaskPhaseRun
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.teams.infrastructure.team_models import TaskAssignment


def state_of(task: Task) -> EngineeringState:
    return EngineeringState(
        TaskStatus(task.status),
        Stage(task.stage),
        WaitReason(task.wait_reason or "NONE"),
        task.requirement_version,
        task.manual_takeover,
    )


class LifecycleConflict(ValueError):
    pass


async def record_transition(
    session: AsyncSession,
    task_id: UUID,
    action: Action,
    *,
    expected_version: int,
    actor: str,
    wait_reason: WaitReason = WaitReason.NONE,
    external_wait: bool = False,
) -> EngineeringState:
    """Atomic state/history update; caller owns commit and external authority."""
    if not actor.strip():
        raise ValueError("A transition requires a known actor")
    task = await session.scalar(
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise LookupError("Task not found")
    if task.lifecycle_version != expected_version:
        raise LifecycleConflict("Task changed since the operation began")
    before = state_of(task)
    after = transition(before, action, wait_reason=wait_reason, external_wait=external_wait)
    now = datetime.now(UTC)
    phases = await session.scalars(
        select(TaskPhaseRun)
        .where(
            TaskPhaseRun.task_id == task_id,
            TaskPhaseRun.finished_at.is_(None),
        )
        .with_for_update()
    )
    for phase in phases:
        phase.finished_at = now
    task.status, task.stage, task.wait_reason = (
        after.status.value,
        after.stage.value,
        after.wait_reason.value,
    )
    task.requirement_version, task.manual_takeover = (
        after.requirement_version,
        after.manual_takeover,
    )
    if after.status == TaskStatus.ACTIVE and task.started_at is None:
        task.started_at = now
    if after.status == TaskStatus.MERGED:
        task.completed_at = now
    assignments = await session.scalars(
        select(TaskAssignment)
        .where(
            TaskAssignment.task_id == task_id,
            TaskAssignment.status.in_(["QUEUED", "RUNNING"]),
        )
        .with_for_update()
    )
    for assignment in assignments:
        if after.status == TaskStatus.ACTIVE:
            assignment.status = "RUNNING"
            assignment.started_at = assignment.started_at or now
        elif after.status in {TaskStatus.MERGED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
            assignment.status = (
                "COMPLETED" if after.status == TaskStatus.MERGED else after.status.value
            )
            assignment.completed_at = now
    task.lifecycle_version += 1
    await enqueue_status(
        session, task_id, task.lifecycle_version, after.status.value, after.stage.value
    )
    session.add(
        TaskPhaseRun(
            task_id=task_id,
            status=after.status.value,
            stage=after.stage.value,
            wait_reason=after.wait_reason.value,
            actor=actor,
            requirement_version=after.requirement_version,
            started_at=now,
            finished_at=now
            if after.status in {TaskStatus.MERGED, TaskStatus.CANCELLED, TaskStatus.FAILED}
            else None,
        )
    )
    session.add(
        TaskEvent(
            task_id=task_id,
            source="engineering-v2",
            event_type="TASK_LIFECYCLE_CHANGED",
            payload={
                "actor": actor,
                "action": action.value,
                "from_status": before.status.value,
                "to_status": after.status.value,
                "from_stage": before.stage.value,
                "to_stage": after.stage.value,
                "wait_reason": after.wait_reason.value,
                "requirement_version": after.requirement_version,
                "version": task.lifecycle_version,
            },
            created_at=now,
        )
    )
    await session.flush()
    return after
