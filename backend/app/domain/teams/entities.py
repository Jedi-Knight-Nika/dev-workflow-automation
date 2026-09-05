import uuid
from dataclasses import dataclass
from enum import StrEnum


class TeamStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class Team:
    id: uuid.UUID
    name: str
    description: str = ""
    status: TeamStatus = TeamStatus.ACTIVE
    max_concurrent_tasks: int = 1
    repository_ids: tuple[uuid.UUID, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Team name cannot be blank")
        if not 1 <= self.max_concurrent_tasks <= 32:
            raise ValueError("Team concurrency must be between 1 and 32")
