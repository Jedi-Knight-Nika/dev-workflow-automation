import sqlite3
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import sqlite

from app.agent_runtime.infrastructure.reservations import consumed_cost


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "receipts,expected",
    [
        ([], Decimal(0)),
        ([("COMPLETED", 0, 9), ("FAILED", None, 2)], Decimal(2)),
        ([("COMPLETED", 3, 9), ("FAILED", None, 2)], Decimal(5)),
        ([("COMPLETED", None, None)], None),
        ([("RUNNING", 3, 9)], None),
    ],
)
async def test_consumed_cost_aggregates_without_losing_unknown_or_zero(receipts, expected):
    task_id = uuid4()
    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE ai_runs (task_id TEXT, status TEXT, "
            "provider_cost_usd NUMERIC, calculated_cost_usd NUMERIC)"
        )
        connection.executemany(
            "INSERT INTO ai_runs VALUES (?, ?, ?, ?)",
            [(task_id.hex, *row) for row in receipts],
        )
        # Other tasks must not affect this task's total or unknown-cost state.
        connection.execute(
            "INSERT INTO ai_runs VALUES (?, 'RUNNING', NULL, NULL)", (uuid4().hex,)
        )

        async def execute(statement):
            sql = str(
                statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            )
            return Mock(one=Mock(return_value=connection.execute(sql).fetchone()))

        session = SimpleNamespace(execute=AsyncMock(side_effect=execute))
        assert await consumed_cost(session, task_id) == expected
        session.execute.assert_awaited_once()
