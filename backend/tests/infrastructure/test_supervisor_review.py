import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.intake.domain.events import Event
from app.platform.configuration.settings import Settings
from app.supervisor.infrastructure import review


@pytest.mark.asyncio
async def test_review_wakes_with_task_memory_and_current_evidence(monkeypatch):
    task = SimpleNamespace(
        id=uuid4(),
        title="Move window",
        description="Preserve contents",
        stage="REVIEWING",
        current_revision="a" * 40,
        pull_request_number=10,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(status="COMPLETED", failure_code=None)),
        scalars=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [SimpleNamespace(status="PASSED", exit_code=0)]
            )
        ),
    )
    monkeypatch.setattr(
        review,
        "task_memory",
        AsyncMock(return_value=[{"decision": {"physical_object": "window container"}}]),
    )
    event = Event(
        "github",
        "comment:1",
        "comment",
        "owner",
        "nice go merje baby",
        str(task.id),
        task.current_revision,
        True,
    )
    agent = await review.review_supervisor(None, session, Settings(), task, event)
    assert agent.role_kind == "SUPERVISOR"
    packet = json.loads(agent.messages[1]["content"])
    assert packet["memory"][0]["decision"]["physical_object"] == "window container"
    assert packet["current_sha"] == task.current_revision
    assert packet["validation"][0]["status"] == "PASSED"
    assert packet["latest_event"]["body"] == event.body
