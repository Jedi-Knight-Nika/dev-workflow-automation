import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FailureEvent, HealthState, Job


class SqlAlchemyResilienceQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def health(self) -> list[dict[str, object]]:
        records = (
            await self._session.scalars(
                select(HealthState).order_by(HealthState.resource_type, HealthState.resource_id)
            )
        ).all()
        return [
            {
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "status": row.status,
                "circuit_state": row.circuit_state,
                "consecutive_failures": row.consecutive_failures,
                "last_success_at": row.last_success_at,
                "last_failure_at": row.last_failure_at,
                "next_probe_at": row.next_probe_at,
                "last_error_class": row.last_error_class,
            }
            for row in records
        ]

    async def failure_history(self, job_id: uuid.UUID) -> list[dict[str, object]]:
        records = (
            await self._session.scalars(
                select(FailureEvent)
                .where(FailureEvent.job_id == job_id)
                .order_by(FailureEvent.created_at.desc())
            )
        ).all()
        return [self._failure(row) for row in records]

    async def blocking_reason(self, task_id: uuid.UUID) -> dict[str, object] | None:
        job = await self._session.scalar(
            select(Job)
            .where(
                Job.task_id == task_id,
                Job.state.in_(
                    [
                        "WAITING_PROVIDER",
                        "WAITING_INTEGRATION",
                        "WAITING_CONFIGURATION",
                        "WAITING_HUMAN",
                    ]
                ),
            )
            .order_by(Job.updated_at.desc())
            .limit(1)
        )
        if job is None:
            return None
        failure = await self._session.scalar(
            select(FailureEvent)
            .where(FailureEvent.job_id == job.id)
            .order_by(FailureEvent.created_at.desc())
            .limit(1)
        )
        return {
            "task_id": task_id,
            "job_id": job.id,
            "job_state": job.state.value,
            "failure": self._failure(failure) if failure else None,
            "recovery": (
                "AUTOMATIC"
                if job.state.value in {"WAITING_PROVIDER", "WAITING_INTEGRATION"}
                else "USER_ACTION_REQUIRED"
            ),
        }

    @staticmethod
    def _failure(row: FailureEvent) -> dict[str, object]:
        return {
            "id": row.id,
            "failure_class": row.failure_class,
            "fingerprint": row.fingerprint,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "safe_message": row.safe_message,
            "retryable": row.retryable,
            "created_at": row.created_at,
        }
