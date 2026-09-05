from app.application.ports.task_reconciliation import (
    ReconciliationResult,
    TaskReconciliationGateway,
)


class ReconcileExternalTasks:
    def __init__(self, gateway: TaskReconciliationGateway) -> None:
        self._gateway = gateway

    async def execute(self) -> ReconciliationResult:
        return await self._gateway.reconcile_due()
