import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.delivery.infrastructure import workflow
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.models import ReviewCycle, ValidationRun
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure import engineering_events, review_text
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import TeamAutomationPolicy
from tests.infrastructure.test_delivery import SHA, fixture_payloads
from tests.integration.test_enrollment_and_costs import scenario

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("changed", [None, "edited", "deleted", "failed_ci"])
async def test_poll_classify_and_merge_rechecks_live_comment_without_developer_run(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: str | None,
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (
        team_id,
        repo_id,
        task_id,
        settings,
    ):
        jobs = SqlPhaseJobs(postgres_session_factory, "approval-test", 60)
        validated_at = datetime.now(UTC) - timedelta(minutes=2)
        async with postgres_session_factory.begin() as session:
            policy = await session.get(TeamAutomationPolicy, team_id)
            assert policy
            policy.configuration = {
                **policy.configuration,
                "auto_merge": True,
                "reviewer_scope": "any_human",
                "require_formal_approval": False,
                "required_checks": ["test"],
            }
        for action in (Action.START, Action.IMPLEMENTED):
            lease = await jobs.claim()
            assert lease
            await jobs.complete(lease, action)
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task
            task.current_revision, task.pull_request_number = SHA, 1
            session.add(
                ValidationRun(
                    task_id=task_id,
                    head_sha=SHA,
                    requirement_version=1,
                    command=["test"],
                    exit_code=0,
                    status="PASSED",
                    finished_at=validated_at,
                )
            )
        for action in (Action.VALIDATION_PASSED, Action.PUBLISHED):
            lease = await jobs.claim()
            assert lease
            await jobs.complete(lease, action)
        data, writes = fixture_payloads(), []
        comments = [
            {
                "id": 30,
                "body": "lgtm",
                "user": {"id": 7, "type": "User"},
                "updated_at": (validated_at + timedelta(minutes=1)).isoformat(),
            }
        ]
        data["/repos/acme/repo/pulls/1/reviews"] = []
        data["/repos/acme/repo/issues/1/comments"] = comments
        data["/repos/acme/repo/pulls/1/comments"] = []

        def respond(request: httpx.Request) -> httpx.Response:
            if request.method == "PUT":
                writes.append(request)
                assert json.loads(request.content)["sha"] == SHA
                return httpx.Response(200, json={"merged": True, "sha": "c" * 40})
            return httpx.Response(200, json=data[request.url.path])

        def client(_token: str) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url="https://api.github.com", transport=httpx.MockTransport(respond)
            )

        for module in (engineering_events, workflow):
            monkeypatch.setattr(module, "github_token", AsyncMock(return_value="test-only"))
            monkeypatch.setattr(module, "github_client", client)
        interpreter = AsyncMock(side_effect=AssertionError("LGTM must not use paid inference"))
        monkeypatch.setattr(review_text.CloudInterpreter, "interpret", interpreter)
        settings.local_event_interpreter = False
        settings.interpreter_cloud_models = ["openai/test-only"]
        # Polling discovers a comment even if its webhook was missed. Two polls
        # persist only one snapshot and cannot merge until interpretation finishes.
        async with postgres_session_factory.begin() as session:
            task, repo = await session.get(Task, task_id), await session.get(Repository, repo_id)
            assert task and repo
            for attempt in range(2):
                await engineering_events.github_event(
                    session, task, repo, "periodic_recheck", {"attempt": attempt}
                )
            pending = list(
                await session.scalars(
                    select(ReviewCycle).where(
                        ReviewCycle.task_id == task_id, ReviewCycle.decision == "CLASSIFY_PENDING"
                    )
                )
            )
            assert len(pending) == 1 and task.status == "WAITING_EXTERNAL"
        assert await review_text.process_review_text(postgres_session_factory, settings)
        interpreter.assert_not_called()
        lease = await jobs.claim()
        assert lease and lease.action == "MERGE_PR"
        # Changes between authorization and execution must be caught by the final
        # fetch. A previously approved message cannot authorize the edited version.
        if changed == "edited":
            comments[0]["body"] = "Wait, do not merge"
        elif changed == "deleted":
            comments.clear()
        elif changed == "failed_ci":
            data[f"/repos/acme/repo/commits/{SHA}/check-runs"]["check_runs"][0]["conclusion"] = (
                "failure"
            )
        action = await workflow.merge_phase(postgres_session_factory, lease)
        assert action == (Action.MERGE_RECHECK if changed else Action.MERGED)
        await jobs.complete(lease, action)
        assert len(writes) == (0 if changed else 1)
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            assert task and task.status == ("WAITING_EXTERNAL" if changed else "MERGED")
