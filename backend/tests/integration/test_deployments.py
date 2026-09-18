from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.activity.application.ports import ActivityScope, ActivityWindow
from app.activity.infrastructure.models import ActivityEvent
from app.activity.infrastructure.projector import ActivityProjector
from app.activity.infrastructure.queries import SqlActivityQueries
from app.delivery.domain.deployments import github_deployment
from app.delivery.infrastructure.deployment_models import DeploymentObservation
from app.delivery.infrastructure.deployments import SqlDeploymentQueries
from app.delivery.infrastructure.merge_history import observe_merge
from app.engineering.infrastructure.task_models import Task, TaskEvent, TaskRepositoryScope
from app.intake.infrastructure.github_events import process_github_event
from app.repositories.infrastructure.models import Repository
from tests.integration.test_activity import activity_tasks as activity_tasks  # noqa: PLC0414
from tests.integration.test_activity import window


def payload(repo, state="success", id=42, *, sha=None):
    now = datetime.now(UTC)
    return {
        "repository": {"id": str(repo)},
        "deployment": {
            "id": 10,
            "sha": sha or "a" * 40,
            "environment": "production",
            "production_environment": True,
            "created_at": (now - timedelta(minutes=10)).isoformat(),
            "payload": {"secret": "private"},
            "description": "private description",
        },
        "deployment_status": {
            "id": id,
            "state": state,
            "created_at": (now - timedelta(minutes=1)).isoformat(),
            "log_url": "https://private.test/output?secret=private",
        },
    }


async def test_deployment_history_deduplicates_projects_late_matches_and_keeps_orphans(
    activity_tasks,
):
    factory, _, task_id, other_id = activity_tasks
    repo_id, secondary_id = uuid4(), uuid4()
    start, end = datetime.now(UTC) - timedelta(days=1), datetime.now(UTC) + timedelta(minutes=1)
    try:
        async with factory.begin() as session:
            session.add(
                Repository(
                    id=repo_id,
                    owner="test",
                    name="deployment",
                    external_repo_id=str(repo_id),
                    clone_url="https://example.test/repo",
                )
            )
            await session.flush()
            session.add(
                Repository(
                    id=secondary_id,
                    owner="test",
                    name="secondary",
                    external_repo_id=str(secondary_id),
                    clone_url="https://example.test/secondary",
                )
            )
            await session.flush()
            session.add(TaskRepositoryScope(task_id=task_id, repository_id=secondary_id))
            task = await session.get(Task, task_id)
            task.repository_id, task.current_revision = repo_id, "a" * 40
            task.created_at = start
            success = payload(repo_id)
            for _ in range(2):
                await process_github_event(session, "deployment_status", success)
            # Creation arrives late, and a deployment with no matching task stays queryable.
            await process_github_event(session, "deployment", success)
            orphan = payload(repo_id, sha="b" * 40, id=43)
            orphan["deployment"]["id"] = 11
            await process_github_event(session, "deployment_status", orphan)
            # Checking out an already-deployed base must not attribute that older
            # deployment to a task that did not exist yet.
            older = payload(repo_id, id=44)
            older["deployment"].update(id=12, created_at=(start - timedelta(hours=2)).isoformat())
            older["deployment_status"]["created_at"] = (start - timedelta(hours=1)).isoformat()
            await process_github_event(session, "deployment_status", older)
            assert task.status == "NEW" and task.lifecycle_version == 1
        history = await SqlDeploymentQueries(factory).history(start, end, repo_id, 100)
        assert len(history["events"]) == 3
        assert "secret" not in str(history) and "private" not in str(history)
        assert history["events"][0]["status"] == "CREATED"
        assert (await SqlDeploymentQueries(factory).history(start, end, repo_id, 1))["truncated"]
        projector = ActivityProjector(factory)
        await projector.project()
        await projector.project()
        page = await SqlActivityQueries(factory, 100, 20).events(window(task_id), 0, None, 100)
        assert len(page["events"]) == 2
        assert {event["kind"] for event in page["events"]} == {"DEPLOYMENT_STATUS_CHANGED"}
        assert {event["payload"]["status"] for event in page["events"]} == {"CREATED", "SUCCESS"}
        secondary = await SqlActivityQueries(factory, 100, 20).events(
            ActivityWindow(ActivityScope("repository", str(secondary_id)), start, end), 0, None, 100
        )
        assert not secondary["events"]
        # Later confirmed merge evidence can associate an earlier committed observation.
        async with factory.begin() as session:
            task = await session.get(Task, other_id)
            task.repository_id = repo_id
            task.created_at = start
            await observe_merge(session, task, repo_id, "b" * 40)
            await observe_merge(session, task, repo_id, "b" * 40)
            assert task.status == "NEW"
            observations = list(
                await session.scalars(
                    select(TaskEvent).where(
                        TaskEvent.task_id == other_id,
                        TaskEvent.event_type == "GITHUB_MERGE_OBSERVED",
                    )
                )
            )
            assert len(observations) == 1
        await projector.project()
        page = await SqlActivityQueries(factory, 100, 20).events(window(other_id), 0, None, 100)
        assert any(event["kind"] == "DEPLOYMENT_STATUS_CHANGED" for event in page["events"])
        async with factory() as session:
            assert (
                len(
                    list(
                        await session.scalars(
                            select(DeploymentObservation).where(
                                DeploymentObservation.repository_id == repo_id
                            )
                        )
                    )
                )
                == 4
            )
            assert (
                len(
                    list(
                        await session.scalars(
                            select(ActivityEvent).where(
                                ActivityEvent.source_type == "deployment",
                                ActivityEvent.task_id.in_([task_id, other_id]),
                            )
                        )
                    )
                )
                == 3
            )
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(TaskRepositoryScope).where(TaskRepositoryScope.repository_id == secondary_id)
            )
            await session.execute(
                delete(Repository).where(Repository.id.in_([repo_id, secondary_id]))
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha", "main"),
        ("id", True),
        ("created_at", "2026-09-15"),
        ("environment", "bad\nenvironment"),
        ("environment", "x" * 256),
    ],
)
def test_invalid_deployment_metadata_is_not_persisted(field, value):
    data = payload(uuid4())
    data["deployment"][field] = value
    assert github_deployment("deployment_status", data) is None


def test_unavailable_production_flag_stays_unknown_and_invalid_outcomes_are_ignored():
    data = payload(uuid4())
    data["deployment"]["production_environment"] = "true"
    assert github_deployment("deployment_status", data).production is None
    data["deployment_status"]["state"] = "unknown-private-value"
    assert github_deployment("deployment_status", data) is None


async def test_deployment_query_rejects_unbounded_ranges_and_missing_repositories(activity_tasks):
    factory, _, _, _ = activity_tasks
    queries = SqlDeploymentQueries(factory)
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        await queries.history(now - timedelta(days=91), now, None, 100)
    with pytest.raises(LookupError):
        await queries.history(now - timedelta(days=1), now, uuid4(), 100)
