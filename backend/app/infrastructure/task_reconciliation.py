from app.application.ports.task_reconciliation import (
    ReconciliationResult,
    TaskReconciliationGateway,
)


class CompositeTaskReconciliation:
    def __init__(self, *gateways: TaskReconciliationGateway) -> None:
        self._gateways = gateways

    async def reconcile_due(self) -> ReconciliationResult:
        processed = False
        imported = 0
        updated = 0
        for gateway in self._gateways:
            result = await gateway.reconcile_due()
            processed = processed or result.processed
            imported += result.imported
            updated += result.updated
        return ReconciliationResult(processed=processed, imported=imported, updated=updated)
