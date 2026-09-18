from typing import Protocol
from uuid import UUID

from app.engineering.application.jobs import PhaseLease
from app.engineering.domain.lifecycle import Action


class DevelopmentRecovery(Protocol):
    async def validate_candidate(self, lease: PhaseLease, session_id: UUID) -> bool: ...
    async def repair(self, lease: PhaseLease, session_id: UUID) -> bool: ...
    async def rollover(self, lease: PhaseLease, requirement_version: int, summary: str) -> None: ...


class ResumablePhaseExecutor(Protocol):
    async def execute(
        self,
        lease: PhaseLease,
        *,
        compaction: bool = False,
        compacted: bool = False,
        continuity: bool = False,
    ) -> Action: ...
