from app.application.ports.startup_maintenance import StartupMaintenance


class RunStartupMaintenance:
    def __init__(self, maintenance: StartupMaintenance) -> None:
        self._maintenance = maintenance

    async def execute(self) -> None:
        await self._maintenance.recover_and_reconcile()
