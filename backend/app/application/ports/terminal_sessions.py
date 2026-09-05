import uuid
from dataclasses import dataclass
from typing import Protocol


class TerminalUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenTerminalCommand:
    task_id: uuid.UUID
    node_id: uuid.UUID | None
    cols: int = 120
    rows: int = 32


@dataclass(frozen=True, slots=True)
class TerminalAccess:
    session_id: uuid.UUID
    token: str
    status: str
    cols: int
    rows: int


class TerminalSessionGateway(Protocol):
    async def open(self, command: OpenTerminalCommand) -> TerminalAccess: ...
    async def close(self, session_id: uuid.UUID) -> bool: ...
