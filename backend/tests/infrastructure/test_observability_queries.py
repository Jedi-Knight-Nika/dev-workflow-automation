from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agent_runtime.infrastructure.models import AIRun
from app.observability.infrastructure.persistence import SqlObservabilityStore, receipt_totals


def test_runner_receipt_totals_preserve_zero_cost_and_unknown_measurements():
    now = datetime.now(UTC)
    receipts = [
        AIRun(
            provider_cost_usd=Decimal(0),
            calculated_cost_usd=Decimal(10),
            input_tokens=100,
            output_tokens=20,
            provider_duration_ms=1000,
            role_kind="DEVELOPER",
            started_at=now - timedelta(seconds=10),
            finished_at=None,
        ),
        AIRun(
            provider_cost_usd=None,
            calculated_cost_usd=None,
            input_tokens=None,
            output_tokens=5,
            provider_duration_ms=None,
            role_kind="SUPERVISOR",
            started_at=now - timedelta(seconds=5),
            finished_at=now,
        ),
    ]
    result = receipt_totals(receipts, now)
    assert result["known_cost_usd"] == "0"
    assert result["unknown_cost_runs"] == 1
    assert result["input_tokens"] is None
    assert result["output_tokens"] == 25
    assert result["ai_active_seconds"] is None
    assert result["developer_active_seconds"] == 10
    empty = receipt_totals([], now)
    assert empty["input_tokens"] == empty["output_tokens"] == 0
    assert empty["ai_active_seconds"] is None


@pytest.mark.asyncio
async def test_empty_runner_list_skips_related_database_reads():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=Mock(all=Mock(return_value=[]))),
        scalars=AsyncMock(),
    )
    context = AsyncMock()
    context.__aenter__.return_value = session
    store = SqlObservabilityStore(Mock(return_value=context))
    assert await store.runners(active=True) == []
    session.execute.assert_awaited_once()
    session.scalars.assert_not_awaited()
