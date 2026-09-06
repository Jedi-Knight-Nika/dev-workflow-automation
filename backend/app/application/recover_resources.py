import uuid

from app.application.ports.resilience import ResilienceStore


class RecoveryManager:
    """Coordinates durable, gradual recovery without owning scheduler policy."""

    def __init__(self, store: ResilienceStore, recovery_batch_size: int = 2) -> None:
        self._store = store
        self._recovery_batch_size = recovery_batch_size

    async def recover_due_resources(self) -> int:
        return await self._store.recover_due_resources(self._recovery_batch_size)

    async def record_job_success(self, job_id: uuid.UUID) -> None:
        await self._store.record_job_success(job_id)
