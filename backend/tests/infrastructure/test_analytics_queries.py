from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.analytics.infrastructure.persistence import SqlAnalyticsFacts


def facts_with_session(session):
    context = AsyncMock()
    context.__aenter__.return_value = session
    return SqlAnalyticsFacts(Mock(return_value=context))


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 5001])
async def test_analytics_checks_cohort_before_related_queries(size):
    session = SimpleNamespace(scalars=AsyncMock(return_value=[object()] * size))
    facts = facts_with_session(session)
    if size:
        with pytest.raises(ValueError, match="5000 tasks"):
            await facts.tasks(datetime.now(UTC))
    else:
        assert await facts.tasks(datetime.now(UTC)) == []
    assert session.scalars.await_count == 1


@pytest.mark.asyncio
async def test_analytics_uses_grouped_review_and_validation_counts():
    now = datetime.now(UTC)
    task_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        title="Task",
        team_id=None,
        repository_id=None,
        external_key=None,
        description="",
        status="NEW",
        created_at=now,
        completed_at=None,
        estimate=None,
        labels=[],
    )
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[[task], [], [], [], [], []]),
        execute=AsyncMock(
            side_effect=[
                Mock(all=Mock(return_value=rows))
                for rows in (
                    [],
                    [(task_id, 2)],
                    [(task_id, 3)],
                    [],
                )
            ]
        ),
    )
    result = await facts_with_session(session).tasks(now)
    assert len(result) == 1
    assert result[0].review_cycles == 2
    assert result[0].validation_failures == 3
    for call in session.execute.call_args_list[1:3]:
        sql = str(call.args[0])
        assert "count(*)" in sql and "GROUP BY" in sql
    assert "CODE_CHANGE" in str(
        session.execute.call_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )
