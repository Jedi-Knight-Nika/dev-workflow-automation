from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from app.analytics.infrastructure import forecast_worker


async def test_empty_candidate_page_does_not_load_history_or_start_write(monkeypatch):
    session = AsyncMock()
    session.scalars.return_value = []
    manager = AsyncMock()
    manager.__aenter__.return_value = session
    sessions = Mock(return_value=manager)
    source = Mock()
    monkeypatch.setattr(forecast_worker, "SqlAnalyticsFacts", source)
    assert await forecast_worker.snapshot_forecasts(sessions, 5) is None
    sessions.begin.assert_not_called()
    source.assert_not_called()


async def test_snapshots_share_one_transaction_and_recheck_started_tasks(monkeypatch):
    identifiers = sorted([uuid4(), uuid4()])
    tasks = [
        SimpleNamespace(id=str(identifier), status="NEW", runs=[]) for identifier in identifiers
    ]
    facts = AsyncMock()
    facts.tasks.side_effect = [tasks, []]
    monkeypatch.setattr(forecast_worker, "SqlAnalyticsFacts", Mock(return_value=facts))
    monkeypatch.setattr(
        forecast_worker,
        "forecast",
        Mock(
            return_value={
                "model_kind": "test",
                "sample_count": 0,
                "confidence": "INSUFFICIENT",
                "estimate": {},
            }
        ),
    )
    session = AsyncMock()
    session.scalars.side_effect = [
        identifiers,
        [],
        [SimpleNamespace(id=identifier, status="NEW") for identifier in identifiers],
        [],
        [identifiers[0]],
    ]
    manager = AsyncMock()
    manager.__aenter__.return_value = session
    sessions = Mock(return_value=manager)
    sessions.begin.return_value = manager
    assert await forecast_worker.snapshot_forecasts(sessions, 5) == identifiers[-1]
    sessions.begin.assert_called_once()
    session.execute.assert_awaited_once()
    params = session.execute.await_args.args[0].compile().params
    assert params["task_id_m0"] == identifiers[1]
    assert "task_id_m1" not in params
