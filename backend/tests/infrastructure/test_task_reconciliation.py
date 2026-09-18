from app.intake.application.ports.task_reconciliation import ReconciliationResult
from app.intake.application.reconcile_tasks import ReconcileExternalTasks
from app.intake.infrastructure.reconciliation import CompositeTaskReconciliation


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


async def test_trello_prefetches_existing_cards_without_per_card_reads(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from uuid import uuid4

    from app.engineering.infrastructure.task_models import Task
    from app.intake.infrastructure import trello_reconciliation as module

    cards = [
        {
            "id": str(uuid4()),
            "short_link": str(offset),
            "name": "Existing card",
            "description": "Details",
            "labels": [],
            "due": None,
            "due_complete": False,
            "list_id": "todo",
            "url": "",
            "raw": {},
        }
        for offset in range(100)
    ]
    tasks = [Task(id=uuid4(), title="Existing card", description="Details") for _ in cards]
    snapshots = [
        SimpleNamespace(task_id=task.id, external_id=card["id"])
        for card, task in zip(cards, tasks, strict=True)
    ]
    integration = SimpleNamespace(
        encrypted_credentials="encrypted", last_synced_at=None, configuration={"board_id": "board"}
    )
    session = AsyncMock()
    session.scalar.return_value = integration
    session.scalars.side_effect = [snapshots, tasks]
    transaction = AsyncMock()
    transaction.__aenter__.return_value = session
    session.begin_nested = Mock(return_value=transaction)
    client = AsyncMock()
    client.list_cards.return_value = cards
    monkeypatch.setattr(module, "TrelloClient", Mock(return_value=client))
    monkeypatch.setattr(module, "cipher", Mock(decrypt=Mock(return_value="unused")))
    engineering = Mock()
    result = await module.SqlAlchemyTrelloTaskReconciliation(
        Mock(return_value=transaction), engineering
    ).reconcile_due()
    assert result.imported == 0 and result.updated == 100
    assert session.scalar.await_count == 1
    assert session.scalars.await_count == 2
    session.get.assert_not_awaited()
    engineering.assert_not_called()
