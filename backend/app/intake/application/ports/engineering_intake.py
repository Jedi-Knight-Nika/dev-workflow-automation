from typing import Protocol
from uuid import UUID


class EngineeringIntake(Protocol):
    async def created(
        self, task_id: UUID, provider: str, external_id: str, identifier: str
    ) -> None: ...
