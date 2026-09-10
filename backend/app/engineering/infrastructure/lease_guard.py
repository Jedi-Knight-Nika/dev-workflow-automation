"""Shared persisted-lease guard for task execution and recovery adapters."""

from datetime import UTC, datetime

from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import WaitReason
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState


def assert_current(job: Job | None, task: Task | None, lease: PhaseLease) -> None:
    if (
        job is None
        or task is None
        or job.task_id != task.id
        or job.lease_token != lease.token
        or job.state != JobState.RUNNING
        or job.lease_expires_at is None
        or job.lease_expires_at <= datetime.now(UTC)
        or task.lifecycle_version != lease.lifecycle_version
        or task.status != "ACTIVE"
        or task.manual_takeover
        or task.archived_at is not None
    ):
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION, "Supervisor lease is no longer current"
        )
