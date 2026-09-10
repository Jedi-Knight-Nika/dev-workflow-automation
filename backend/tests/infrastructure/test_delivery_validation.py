from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.delivery.infrastructure import workflow
from app.teams.domain.automation import AutomationPolicy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statuses,valid", [([], False), (["PASSED"], True), (["PASSED", "FAILED"], False)]
)
async def test_delivery_gate_requires_all_current_revision_checks_to_pass(
    monkeypatch, statuses, valid
):
    task = SimpleNamespace(
        id=uuid4(), team_id=uuid4(), current_revision="head", requirement_version=7
    )
    repository = SimpleNamespace(id=uuid4(), enabled=True, archived_at=None)
    monkeypatch.setattr(workflow, "read_policy", AsyncMock(return_value=AutomationPolicy()))
    session = SimpleNamespace(scalars=AsyncMock(return_value=statuses))
    _, _, validated = await workflow.delivery_gate(session, task, repository)
    assert validated == ("head" if valid else None)
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "output_tail" not in sql
    assert "head_sha = 'head'" in sql
    assert "requirement_version = 7" in sql
