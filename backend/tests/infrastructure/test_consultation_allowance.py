import sqlite3
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import sqlite

from app.engineering.application.jobs import PhaseBlocked
from app.engineering.infrastructure.consultation import consultation_allowance


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows,role,expected",
    [
        ([], "REVIEWER", Decimal(5)),
        ([("REVIEWER", 1, "COMPLETED", 0, 9)], "REVIEWER", Decimal(5)),
        (
            [("DEVELOPER", 1, "COMPLETED", None, 7), ("REVIEWER", 1, "FAILED", 1, 9)],
            "REVIEWER",
            Decimal(2),
        ),
        ([("DEVELOPER", 1, "RUNNING", 1, 1)], "REVIEWER", "Reconcile incomplete"),
        ([("DEVELOPER", 1, "FAILED", None, None)], "REVIEWER", "Reconcile incomplete"),
        ([("REVIEWER", 1, "COMPLETED", 5, 1)], "REVIEWER", "spending limit"),
        ([("THINKER", 1, "COMPLETED", 1, 1)], "THINKER", Decimal(4)),
        (
            [("THINKER", 2, "COMPLETED", None, None)],
            "THINKER",
            "A plan already exists",
        ),
    ],
)
async def test_consultation_aggregate_preserves_limits_and_blocker_order(rows, role, expected):
    task = SimpleNamespace(id=uuid4(), requirement_version=2)
    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE ai_runs (task_id TEXT, role_kind TEXT, requirement_version INTEGER, "
            "status TEXT, provider_cost_usd NUMERIC, calculated_cost_usd NUMERIC)"
        )
        connection.executemany(
            "INSERT INTO ai_runs VALUES (?, ?, ?, ?, ?, ?)",
            [(task.id.hex, *row) for row in rows],
        )
        connection.execute(
            "INSERT INTO ai_runs VALUES (?, 'THINKER', 2, 'RUNNING', NULL, NULL)",
            (uuid4().hex,),
        )

        async def execute(statement):
            sql = str(
                statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            )
            return Mock(one=Mock(return_value=connection.execute(sql).fetchone()))

        session = SimpleNamespace(execute=AsyncMock(side_effect=execute))
        if isinstance(expected, str):
            with pytest.raises(PhaseBlocked, match=expected):
                await consultation_allowance(session, task, role, Decimal(10), Decimal(5))
        else:
            assert (
                await consultation_allowance(session, task, role, Decimal(10), Decimal(5))
                == expected
            )
        session.execute.assert_awaited_once()
