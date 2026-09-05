import uuid

from app.application.ports.worker_runtime import WorkerExecution
from app.config import Settings
from app.infrastructure.workers.transport import run_worker


class ConfiguredWorkerRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(self, job_id: uuid.UUID) -> WorkerExecution:
        return await run_worker(self._settings, job_id)
