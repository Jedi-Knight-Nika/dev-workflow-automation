import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import HealthState, Incident, Job, JobState, Notification, TaskEvent, WorkerRun
from app.domain.notifications import IncidentStatus, NotificationStatus
from app.domain.orchestration import (
    CircuitSnapshot,
    CircuitState,
    allow_probe,
    record_success,
)


class SqlAlchemyResilienceStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def recover_due_resources(self, limit: int = 2) -> int:
        now = datetime.now(UTC)
        recovered = 0
        async with self._session_factory() as session:
            resources = (
                await session.scalars(
                    select(HealthState)
                    .where(
                        HealthState.circuit_state == CircuitState.OPEN.value,
                        HealthState.next_probe_at.is_not(None),
                        HealthState.next_probe_at <= now,
                    )
                    .order_by(HealthState.next_probe_at)
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).all()
            for health in resources:
                snapshot = allow_probe(
                    CircuitSnapshot(
                        CircuitState(health.circuit_state),
                        health.consecutive_failures,
                        health.next_probe_at,
                    ),
                    now=now,
                )
                if snapshot.state is not CircuitState.HALF_OPEN:
                    continue
                job = await self._waiting_provider_job(session, health.resource_id)
                if job is None:
                    continue
                health.circuit_state = CircuitState.HALF_OPEN.value
                health.next_probe_at = None
                health.probe_job_id = job.id
                job.state = JobState.QUEUED
                job.retry_not_before = None
                job.finished_at = None
                session.add(
                    TaskEvent(
                        task_id=job.task_id,
                        source="SYSTEM",
                        event_type="JOB_RECOVERY_QUEUED",
                        payload={
                            "job_id": str(job.id),
                            "resource_type": health.resource_type,
                            "resource_id": health.resource_id,
                        },
                    )
                )
                recovered += 1
            await session.commit()
        return recovered

    async def record_job_success(self, job_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            worker_run = await session.scalar(
                select(WorkerRun)
                .where(WorkerRun.job_id == job_id)
                .order_by(WorkerRun.created_at.desc())
                .limit(1)
            )
            if worker_run is None:
                return
            health = await session.scalar(
                select(HealthState)
                .where(
                    HealthState.resource_type == "PROVIDER",
                    HealthState.resource_id == worker_run.provider,
                )
                .with_for_update()
            )
            if health is None:
                return
            was_unhealthy = health.circuit_state != CircuitState.CLOSED.value
            snapshot = record_success(
                CircuitSnapshot(
                    CircuitState(health.circuit_state),
                    health.consecutive_failures,
                    health.next_probe_at,
                )
            )
            health.status = "HEALTHY"
            health.circuit_state = snapshot.state.value
            health.consecutive_failures = snapshot.consecutive_failures
            health.next_probe_at = None
            health.last_success_at = now
            health.last_error_class = None
            health.probe_job_id = None
            if health.failure_fingerprint:
                incident = await session.scalar(
                    select(Incident)
                    .where(Incident.fingerprint == health.failure_fingerprint)
                    .with_for_update()
                )
                if incident and incident.status != IncidentStatus.RESOLVED.value:
                    incident.status = IncidentStatus.RESOLVED.value
                    incident.resolved_at = now
                    notifications = (
                        await session.scalars(
                            select(Notification).where(Notification.incident_id == incident.id)
                        )
                    ).all()
                    for notification in notifications:
                        notification.status = NotificationStatus.RESOLVED.value
                        notification.resolved_at = now
            if was_unhealthy:
                job = await session.get(Job, job_id)
                if job:
                    session.add(
                        TaskEvent(
                            task_id=job.task_id,
                            source="SYSTEM",
                            event_type="PROVIDER_RECOVERED",
                            payload={"provider": worker_run.provider, "job_id": str(job_id)},
                        )
                    )
            await session.commit()

    @staticmethod
    async def _waiting_provider_job(session: AsyncSession, provider: str) -> Job | None:
        return cast(
            Job | None,
            await session.scalar(
                select(Job)
                .join(WorkerRun, WorkerRun.job_id == Job.id)
                .where(
                    Job.state == JobState.WAITING_PROVIDER,
                    WorkerRun.provider == provider,
                )
                .order_by(Job.priority, Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            ),
        )
