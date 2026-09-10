from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.delivery.infrastructure import publication
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import Action


@pytest.mark.asyncio
@pytest.mark.parametrize("validated,stale", [(False, False), (True, False), (True, True)])
async def test_publication_preserves_gate_push_pr_and_persist_order(monkeypatch, validated, stale):
    events = []
    sha = "a" * 40
    task = SimpleNamespace(
        id=uuid4(), branch_name=f"agent/task-{uuid4()}", title="Fix panel", external_key=None
    )
    lease = SimpleNamespace(job_id=uuid4(), token=uuid4(), lifecycle_version=1)
    current = SimpleNamespace(lifecycle_version=2 if stale else 1)
    session = SimpleNamespace(get=AsyncMock(return_value=current))

    @asynccontextmanager
    async def transaction():
        yield session

    sessions = Mock(side_effect=transaction)
    sessions.begin = transaction

    async def gate(*args):
        events.append("gate")
        return None, None, sha if validated else None

    async def push(client, settings, mounts, manifest, token, name):
        events.append("push")
        assert manifest.expected_sha == sha
        assert manifest.base_branch == "release"

    async def publish(**kwargs):
        events.append("pr")
        assert kwargs["expected_sha"] == sha
        assert kwargs["base"] == "release"
        return {"number": 10, "html_url": "https://example.test/pull/10"}

    monkeypatch.setattr(publication, "delivery_gate", gate)
    monkeypatch.setattr(publication, "github_token", AsyncMock(return_value="test-only"))
    mounts = Mock()
    monkeypatch.setattr(publication, "phase_mounts", mounts)
    monkeypatch.setattr(publication, "run_git", push)
    monkeypatch.setattr(publication, "github_client", lambda token: transaction())
    monkeypatch.setattr(publication, "GitHubDelivery", lambda *a: SimpleNamespace(publish=publish))
    args = (
        sessions,
        None,
        None,
        lease,
        task,
        SimpleNamespace(checkpoint={"base_branch": "release", "summary": "fix: repair panel"}),
        SimpleNamespace(owner="owner", name="repository", default_branch="main"),
    )
    if not validated:
        with pytest.raises(PhaseBlocked):
            await publication.publish_phase(*args)
        mounts.assert_not_called()
        assert events == ["gate"]
    elif stale:
        with pytest.raises(ValueError, match="Task changed"):
            await publication.publish_phase(*args)
        assert not hasattr(current, "pull_request_number")
        assert events == ["gate", "push", "pr"]
    else:
        assert await publication.publish_phase(*args) == Action.PUBLISHED
        assert current.pull_request_number == 10
        assert events == ["gate", "push", "pr"]
