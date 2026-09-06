import uuid
from typing import Protocol


class ResilienceStore(Protocol):
    async def recover_due_resources(self, limit: int = 2) -> int: ...

    async def record_job_success(self, job_id: uuid.UUID) -> None: ...
