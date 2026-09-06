from app.application.ports.task_reconciliation import ReconciliationResult
from app.application.reconcile_tasks import ReconcileExternalTasks
from app.infrastructure.task_reconciliation import CompositeTaskReconciliation


class StubReconciliationGateway:
    called = False

    async def reconcile_due(self) -> ReconciliationResult:
        self.called = True
        return ReconciliationResult(processed=True, imported=2, updated=3)


async def test_reconcile_external_tasks_delegates_to_gateway() -> None:
    gateway = StubReconciliationGateway()

    result = await ReconcileExternalTasks(gateway).execute()

    assert gateway.called
    assert result == ReconciliationResult(processed=True, imported=2, updated=3)


async def test_composite_reconciliation_aggregates_providers() -> None:
    first = StubReconciliationGateway()
    second = StubReconciliationGateway()

    result = await CompositeTaskReconciliation(first, second).reconcile_due()

    assert first.called and second.called
    assert result == ReconciliationResult(processed=True, imported=4, updated=6)
