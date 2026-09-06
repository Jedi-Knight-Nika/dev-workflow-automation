import uuid
from typing import Protocol


class ResilienceQueries(Protocol):
    async def health(self) -> list[dict[str, object]]: ...

    async def failure_history(self, job_id: uuid.UUID) -> list[dict[str, object]]: ...

    async def blocking_reason(self, task_id: uuid.UUID) -> dict[str, object] | None: ...
