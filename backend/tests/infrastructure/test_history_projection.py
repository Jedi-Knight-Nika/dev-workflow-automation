from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.engineering.infrastructure.history import SqlAlchemyTaskHistoryQueries


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["metrics", "live_execution"])
async def test_history_reads_omit_unneeded_receipt_payloads(operation):
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        scalars=AsyncMock(return_value=Mock(all=Mock(return_value=[]))),
    )
    queries = SqlAlchemyTaskHistoryQueries(session)
    await getattr(queries, operation)(uuid4())
    call = session.scalars if operation == "metrics" else session.scalar
    statement = call.call_args.args[0]
    projection = str(statement.compile(dialect=postgresql.dialect())).split("FROM", 1)[0]
    assert "ai_runs.artifact" not in projection
    assert "ai_runs.raw_usage" not in projection
    assert "ai_runs.model" in projection
    if operation == "metrics":
        assert "ai_runs.token_efficiency" not in projection
        assert "ai_runs.input_tokens" in projection
        assert "ai_runs.provider_cost_usd" in projection
    else:
        assert "ai_runs.token_efficiency" in projection
        assert "ai_runs.input_tokens" not in projection
