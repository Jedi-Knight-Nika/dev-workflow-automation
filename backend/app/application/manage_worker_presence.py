from app.application.ports.worker_presence import WorkerPresence


class ManageWorkerPresence:
    def __init__(self, presence: WorkerPresence) -> None:
        self._presence = presence

    async def online(self) -> None:
        await self._presence.mark_online()

    async def stopped(self) -> None:
        await self._presence.mark_stopped()
