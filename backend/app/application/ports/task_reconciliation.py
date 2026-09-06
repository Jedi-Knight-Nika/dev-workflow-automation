from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconciliationResult:
    processed: bool
    imported: int = 0
    updated: int = 0


class TaskReconciliationGateway(Protocol):
    async def reconcile_due(self) -> ReconciliationResult: ...
