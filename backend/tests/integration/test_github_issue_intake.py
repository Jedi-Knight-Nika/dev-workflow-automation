from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engineering.infrastructure.task_models import Job, Task
from app.intake.infrastructure import github_issues
from app.repositories.infrastructure.models import Repository
from tests.integration.test_v2_enrollment_and_costs import scenario


@pytest.mark.asyncio
async def test_issue_requires_route_actor_and_label_and_deduplicates(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (team_id, repo_id, _, settings):
        settings.github_issue_routes = {
            "acme/repo": {
                "team_id": str(team_id),
                "trigger_label": "engineering",
                "actor_ids": "42",
            }
        }
        monkeypatch.setattr(github_issues, "get_settings", lambda: settings)
        # Deliberately remove paid execution configuration. The ticket must survive.
        from app.platform.configuration import settings as configuration

        monkeypatch.setattr(configuration, "get_settings", lambda: settings)
        issue_id = str(repo_id)
        payload = {
            "action": "opened",
            "sender": {"id": "not-authorized"},
            "issue": {
                "id": issue_id,
                "number": 12,
                "title": "Implement issue",
                "body": "Use the API",
                "state": "open",
                "labels": [{"name": "engineering"}],
            },
        }
        async with postgres_session_factory.begin() as session:
            repo = await session.get(Repository, repo_id)
            assert repo
            await github_issues.issue_event(session, repo, payload)
            assert (
                await session.scalar(select(Task).where(Task.external_key == f"GITHUB-{issue_id}"))
                is None
            )
            payload["sender"] = {"id": "42"}
            repo.enabled = False
            await github_issues.issue_event(session, repo, payload)
            await github_issues.issue_event(session, repo, payload)
            tasks = list(
                await session.scalars(select(Task).where(Task.external_key == f"GITHUB-{issue_id}"))
            )
            assert len(tasks) == 1 and tasks[0].status == "WAITING_HUMAN"
            assert tasks[0].wait_reason == "MISSING_CONFIGURATION"
            assert await session.scalar(select(Job).where(Job.task_id == tasks[0].id)) is None
