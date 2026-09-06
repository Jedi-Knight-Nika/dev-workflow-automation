from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.job_dispatch import ClaimedJob
from app.db.models import Job, JobRole, JobState
from app.infrastructure.persistence.job_operations import acquire_workspace_lease, claim_next_job


class SqlAlchemyJobDispatch:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self._session_factory = session_factory
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds

    async def claim(self) -> ClaimedJob | None:
        async with self._session_factory() as session:
            job = await claim_next_job(session, self._worker_id, self._lease_seconds)
        if job is None:
            return None
        if job.lease_token is None:
            raise RuntimeError("Claimed job is missing its lease token")
        return ClaimedJob(job.id, job.lease_token, job.result)

    async def prepare(self, claimed_job: ClaimedJob) -> bool:
        async with self._session_factory() as session:
            job = await session.get(Job, claimed_job.job_id)
            if job is None or job.lease_token != claimed_job.lease_token:
                return False
            if job.role == JobRole.EXECUTOR and not await acquire_workspace_lease(
                session, job, self._lease_seconds
            ):
                job.state = JobState.QUEUED
                job.worker_id = None
                job.lease_token = None
                job.lease_expires_at = None
                await session.commit()
                return False
            job.state = JobState.RUNNING
            await session.commit()
            return True
