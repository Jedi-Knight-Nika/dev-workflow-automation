from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.agent_runtime.domain.session_changes import SessionChangeMode


class SessionConflict(ValueError):
    pass


@dataclass(frozen=True)
class SessionView:
    session_id: UUID
    generation: int
    has_native_session: bool
    harness: str
    provider: str
    model: str
    state: str
    task_status: str
    lifecycle_version: int
    profile_version: int
    target_harness: str
    target_provider: str
    target_model: str
    keep_native_available: bool
    blocker: str | None


@dataclass(frozen=True)
class ChangeSession:
    session_id: UUID
    lifecycle_version: int
    profile_version: int
    mode: SessionChangeMode
    reason: str

    def __post_init__(self) -> None:
        if self.lifecycle_version < 1 or self.profile_version < 1:
            raise ValueError("Positive versions are required")
        if not 3 <= len(self.reason.strip()) <= 500:
            raise ValueError("Provide a reason of 3–500 characters")


class SessionAdministration(Protocol):
    async def read(self, task_id: UUID) -> SessionView | None: ...
    async def change(self, task_id: UUID, command: ChangeSession) -> SessionView: ...
