from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.analytics.infrastructure import forecast_worker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,has_runs,expected_queries",
    [
        ("WAITING_EXTERNAL", False, 0),
        ("WAITING_HUMAN", True, 0),
        ("PAUSED", False, 0),
        ("ACTIVE", True, 0),
        ("NEW", True, 0),
        ("NEW", False, 1),
        ("ACTIVE", False, 1),
        ("MERGED", True, 1),
        ("FAILED", True, 1),
        ("CANCELLED", False, 1),
    ],
)
async def test_forecast_worker_skips_tasks_that_cannot_change_snapshots(
    monkeypatch, status, has_runs, expected_queries
):
    facts = AsyncMock()
    facts.tasks.return_value = [
        SimpleNamespace(id=str(uuid4()), status=status, runs=[object()] if has_runs else [])
    ]
    monkeypatch.setattr(forecast_worker, "SqlAnalyticsFacts", Mock(return_value=facts))
    # A finalized snapshot needs no write, even for an eligible terminal task.
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(finalized_at=object())))
    transaction = AsyncMock()
    transaction.__aenter__.return_value = session
    sessions = Mock()
    sessions.begin.return_value = transaction
    await forecast_worker.snapshot_forecasts(sessions, minimum=5)
    assert sessions.begin.call_count == expected_queries
    assert session.scalar.await_count == expected_queries
