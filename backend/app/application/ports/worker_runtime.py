import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorkerExecution:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


class WorkerRunner(Protocol):
    async def __call__(self, job_id: uuid.UUID) -> WorkerExecution: ...
