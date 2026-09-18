from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from app.activity.infrastructure.models import ActivityEvent
from app.activity.infrastructure.projector import ActivityProjector
from app.activity.infrastructure.queries import SqlActivityQueries
from app.agent_runtime.domain.request_usage import with_request_count
from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.intake.infrastructure.engineering_events import github_event
from app.platform.scheduling.states import JobState
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.team_models import TeamCapacityChange
from tests.integration.test_activity import activity_tasks as activity_tasks  # noqa: PLC0414
from tests.integration.test_activity import window


async def test_ci_observations_are_transactional_private_idempotent_and_not_reviews(activity_tasks):
    factory, _, task_id, _ = activity_tasks
    repository_id = uuid4()
    try:
        async with factory() as session:
            repo = Repository(
                id=repository_id,
                owner="test",
                name="ci",
                external_repo_id=str(repository_id),
                clone_url="https://example.test/ci",
            )
            session.add(repo)
            task = await session.get(Task, task_id)
            task.pull_request_number, task.current_revision, task.status = 1, "a" * 40, "PAUSED"
            payload = {
                "check_run": {
                    "id": 42,
                    "head_sha": "a" * 40,
                    "conclusion": "failure",
                    "name": "private check",
                    "output": {"text": "private output"},
                }
            }
            for _ in range(2):
                await github_event(session, task, repo, "check_run", payload)
            assert task.status == "PAUSED"
            cycles = list(
                await session.scalars(select(ReviewCycle).where(ReviewCycle.task_id == task_id))
            )
            assert len(cycles) == 1
            # Upgrade a previously misclassified notification, preserving its identity.
            legacy = ActivityEvent(
                task_id=task_id,
                source_type="review",
                source_id=str(cycles[0].id),
                kind="REVIEW_RECEIVED",
                actor_type="human",
                actor="Reviewer",
                occurred_at=cycles[0].created_at,
                projector_version=3,
            )
            session.add(legacy)
            session.add(
                AIRun(
                    task_id=task_id,
                    provider="test",
                    model="model",
                    role_kind="DEVELOPER",
                    prompt_version="test",
                    status="COMPLETED",
                    finished_at=datetime.now(UTC),
                    raw_usage=with_request_count({"private": "secret"}, 3),
                )
            )
            await session.commit()
        projector = ActivityProjector(factory)
        await projector.project()
        await projector.project()
        page = await SqlActivityQueries(factory, 100, 20).events(window(task_id), 0, None, 100)
        checks = [e for e in page["events"] if e["kind"] == "CI_CHECK_UPDATED"]
        assert len(checks) == 1 and checks[0]["payload"]["status"] == "FAILURE"
        assert checks[0]["parents"][0]["kind"] == "CI_NOTIFICATION_RECEIVED"
        assert not any(e["kind"] == "REVIEW_RECEIVED" for e in page["events"])
        assert (
            next(e for e in page["events"] if e["sequence"] == legacy.sequence)["actor_type"]
            == "integration"
        )
        assert (
            next(e for e in page["events"] if e["kind"] == "AI_RUN_COMPLETED")["payload"][
                "request_count"
            ]
            == 3
        )
        assert "private" not in str(page) and "secret" not in str(page)
        async with factory() as session:
            assert (
                len(
                    list(
                        await session.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id))
                    )
                )
                == 1
            )
    finally:
        async with factory() as session:
            await session.execute(delete(Repository).where(Repository.id == repository_id))
            await session.commit()


async def test_live_capacity_refreshes_finished_jobs_with_the_delivered_sequence_fence(
    activity_tasks,
):
    factory, team_id, task_id, _ = activity_tasks
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(
            TeamCapacityChange(team_id=team_id, capacity=1, created_at=now - timedelta(minutes=1))
        )
        job = Job(
            task_id=task_id,
            action="DEVELOPER_TURN",
            state=JobState.RUNNING,
            attempt=1,
            started_at=now - timedelta(seconds=20),
        )
        session.add(job)
        await session.commit()
    projector = ActivityProjector(factory)
    queries = SqlActivityQueries(factory, 100, 20)
    # Direct task/Team scopes retain policy evidence even with no events in range.
    empty = await queries.capacity(window(task_id), 0)
    assert empty["teams"][0]["id"] == str(team_id)
    assert empty["teams"][0]["limits"][0]["capacity"] == 1
    assert empty["teams"][0]["jobs"] == []
    await projector.project()
    flight = await queries.preflight(window(task_id))
    async with factory() as session:
        saved = await session.get(Job, job.id)
        saved.state, saved.finished_at = JobState.SUCCEEDED, datetime.now(UTC)
        session.add(TeamCapacityChange(team_id=team_id, capacity=2))
        # Deterministic validation does not consume a Team agent slot.
        session.add(
            Job(
                task_id=task_id,
                action="RUN_VALIDATION",
                state=JobState.RUNNING,
                attempt=1,
                started_at=now,
            )
        )
        await session.commit()
    await projector.project()
    latest = await queries.preflight(window(task_id))
    stale = await queries.capacity(window(task_id), flight["through_sequence"])
    fresh = await queries.capacity(window(task_id), latest["through_sequence"])
    assert stale["teams"][0]["jobs"][0]["end"] is None
    assert flight["capacity"]["teams"][0]["limits"][-1]["capacity"] == 1
    team = fresh["teams"][0]
    assert len(team["jobs"]) == 1 and team["jobs"][0]["end"] is not None
    assert team["limits"][-1]["capacity"] == 2
    assert fresh["through_sequence"] == latest["through_sequence"]
