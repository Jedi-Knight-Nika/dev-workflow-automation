import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: uuid.UUID
    lease_token: uuid.UUID
    durable_result: dict[str, Any] | None = None


class JobDispatch(Protocol):
    async def claim(self) -> ClaimedJob | None: ...

    async def prepare(self, claimed_job: ClaimedJob) -> bool: ...
