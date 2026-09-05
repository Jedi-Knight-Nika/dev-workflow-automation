import pytest

from app.application.run_startup_maintenance import RunStartupMaintenance


class FakeStartupMaintenance:
    def __init__(self) -> None:
        self.called = False

    async def recover_and_reconcile(self) -> None:
        self.called = True


@pytest.mark.asyncio
async def test_startup_maintenance_delegates_recovery_and_reconciliation() -> None:
    maintenance = FakeStartupMaintenance()
    await RunStartupMaintenance(maintenance).execute()
    assert maintenance.called
