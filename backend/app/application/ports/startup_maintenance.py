from typing import Protocol


class StartupMaintenance(Protocol):
    async def recover_and_reconcile(self) -> None: ...
