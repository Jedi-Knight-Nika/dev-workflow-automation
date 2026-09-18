from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.bounded_recovery import (
    schedule_bounded_repair,
    schedule_candidate_validation,
)
from app.agent_runtime.infrastructure.token_efficiency import SqlTokenEfficiency
from app.engineering.application.jobs import PhaseLease


class SqlDevelopmentRecovery:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def validate_candidate(self, lease: PhaseLease, session_id: UUID) -> bool:
        return await schedule_candidate_validation(self.sessions, lease, session_id)

    async def repair(self, lease: PhaseLease, session_id: UUID) -> bool:
        return await schedule_bounded_repair(self.sessions, lease, session_id)

    async def rollover(self, lease: PhaseLease, requirement_version: int, summary: str) -> None:
        async with self.sessions() as session:
            await SqlTokenEfficiency(session).rollover(
                lease.task_id,
                requirement_version,
                summary,
                job_id=lease.job_id,
                lease_token=lease.token,
            )
