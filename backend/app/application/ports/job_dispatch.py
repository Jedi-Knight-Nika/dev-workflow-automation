import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: uuid.UUID
    lease_token: uuid.UUID


class JobDispatch(Protocol):
    async def claim(self) -> ClaimedJob | None: ...

    async def prepare(self, claimed_job: ClaimedJob) -> bool: ...
