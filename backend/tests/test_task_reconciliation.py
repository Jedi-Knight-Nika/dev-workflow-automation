from app.application.ports.task_reconciliation import ReconciliationResult
from app.application.reconcile_tasks import ReconcileExternalTasks


class StubReconciliationGateway:
    called = False

    async def reconcile_due(self) -> ReconciliationResult:
        self.called = True
        return ReconciliationResult(True, imported=2, updated=3)


async def test_reconcile_external_tasks_delegates_to_gateway() -> None:
    gateway = StubReconciliationGateway()

    result = await ReconcileExternalTasks(gateway).execute()

    assert gateway.called
    assert result == ReconciliationResult(True, imported=2, updated=3)
