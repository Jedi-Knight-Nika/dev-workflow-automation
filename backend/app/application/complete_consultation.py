import uuid
from typing import Any, Protocol


class ConsultationStore(Protocol):
    async def complete(
        self, job_id: uuid.UUID, lease_token: uuid.UUID, result: dict[str, Any]
    ) -> bool: ...


class CompleteConsultation:
    def __init__(self, store: ConsultationStore) -> None:
        self._store = store

    async def execute(
        self, job_id: uuid.UUID, lease_token: uuid.UUID, result: dict[str, Any]
    ) -> bool:
        return await self._store.complete(job_id, lease_token, result)
