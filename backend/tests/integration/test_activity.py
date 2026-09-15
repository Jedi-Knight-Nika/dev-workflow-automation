import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy import event as sql_events

from app.activity.application.ports import ActivityScope, ActivityWindow
from app.activity.infrastructure.files import collect_files
from app.activity.infrastructure.models import ActivityEvent, ActivityFileChange
from app.activity.infrastructure.projector import ActivityProjector
from app.activity.infrastructure.queries import SqlActivityQueries
from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.lifecycle import record_transition
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.models import ReviewCycle, ValidationRun
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.team_models import Team


@pytest.fixture
def activity_sql(postgres_session_factory):
    statements = []
    engine = postgres_session_factory.kw["bind"].sync_engine

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().startswith("SELECT"):
            statements.append(statement)

    sql_events.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        sql_events.remove(engine, "before_cursor_execute", record)


@pytest_asyncio.fixture
async def activity_tasks(postgres_session_factory):
    factory = postgres_session_factory
    team_id, task_id, other_id = uuid4(), uuid4(), uuid4()
    async with factory() as session:
        session.add(Team(id=team_id, name="Activity " + str(team_id)))
        await session.flush()
        session.add_all(
            [
                Task(
                    id=task_id, title="Recorded task", team_id=team_id, project_name="Visual test"
                ),
                Task(id=other_id, title="Outside scope"),
            ]
        )
        await session.commit()
    try:
        yield factory, team_id, task_id, other_id
    finally:
        async with factory() as session:
            await session.execute(delete(Task).where(Task.id.in_([task_id, other_id])))
            await session.execute(delete(Team).where(Team.id == team_id))
            await session.commit()


def window(task_id, start=None):
    return ActivityWindow(
        ActivityScope("task", str(task_id)),
        start or datetime.now(UTC) - timedelta(days=1),
        datetime.now(UTC) + timedelta(minutes=1),
    )


async def test_late_commit_is_not_lost_and_replay_snapshot_is_stable(activity_tasks):
    factory, _, task_id, _ = activity_tasks
    projector = ActivityProjector(factory)
    queries = SqlActivityQueries(factory, 100, 20)
    async with factory() as late:
        first = TaskEvent(
            task_id=task_id, source="engineering", event_type="TASK_CREATED", payload={}
        )
        late.add(first)
        await late.flush()  # Allocate a lower ID without committing it.
        async with factory() as early:
            early.add(
                TaskEvent(
                    task_id=task_id, source="engineering", event_type="TASK_PAUSED", payload={}
                )
            )
            await early.commit()
        await projector.project()
        flight = await queries.preflight(window(task_id))
        before = await queries.events(window(task_id), 0, flight["through_sequence"], 100)
        assert [e["kind"] for e in before["events"]] == ["TASK_PAUSED"]
        await late.commit()
    await asyncio.gather(projector.project(), projector.project())
    frozen = await queries.events(window(task_id), 0, flight["through_sequence"], 100)
    assert frozen["events"] == before["events"]
    following = await queries.events(window(task_id), flight["through_sequence"], None, 100)
    assert [e["kind"] for e in following["events"]] == ["TASK_CREATED"]
    assert following["events"][0]["sequence"] > flight["through_sequence"]


async def test_receipts_messages_and_projection_never_change_business_state(
    activity_tasks, activity_sql
):
    factory, team_id, task_id, other_id = activity_tasks
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                AIRun(
                    task_id=task_id,
                    provider="test",
                    model="model",
                    role_kind="DEVELOPER",
                    prompt_version="test",
                    status="FAILED",
                    started_at=now - timedelta(minutes=1),
                    finished_at=now,
                    raw_usage={"prompt": "secret"},
                ),
                TaskMessage(
                    task_id=task_id,
                    author_type="SYSTEM",
                    author_name="Validator",
                    kind="UPDATE",
                    body="private source text",
                    context={},
                ),
                ValidationRun(
                    task_id=task_id,
                    head_sha="a" * 40,
                    requirement_version=1,
                    command=["test"],
                    status="PASSED",
                    exit_code=0,
                    output_tail="private validation output",
                    started_at=now,
                    finished_at=now,
                ),
                ReviewCycle(
                    task_id=task_id,
                    external_event_id="review",
                    head_sha="a" * 40,
                    actor="Reviewer",
                    decision="APPROVED",
                    feedback={"body": "private review feedback"},
                ),
                TaskEvent(task_id=other_id, source="user", event_type="TASK_CREATED", payload={}),
            ]
        )
        await session.commit()
    activity_sql.clear()
    projector = ActivityProjector(factory)
    await projector.project()
    await projector.project()
    queries = SqlActivityQueries(factory, 100, 20)
    selected = ActivityWindow(
        ActivityScope("team", str(team_id)), now - timedelta(days=1), now + timedelta(minutes=1)
    )
    page = await queries.events(selected, 0, None, 100)
    assert len(page["events"]) == 5
    assert {e["task_id"] for e in page["events"]} == {str(task_id)}
    receipt = next(e for e in page["events"] if e["kind"] == "AI_RUN_COMPLETED")
    assert receipt["payload"]["cost_usd"] is None
    message = next(e for e in page["events"] if e["kind"] == "MESSAGE_SENT")
    assert message["actor_type"] == "system"
    assert {e["kind"] for e in page["events"]} >= {"VALIDATION_CHECK_COMPLETED", "REVIEW_RECEIVED"}
    assert "secret" not in str(page) and "private source text" not in str(page)
    for column in (
        "tasks.description",
        "task_messages.body",
        "validation_runs.output_tail",
        "review_cycles.feedback",
        "ai_runs.token_efficiency",
    ):
        assert all(column not in sql for sql in activity_sql)
    async with factory() as session:
        task = await session.get(Task, task_id)
        assert (task.status, task.stage, task.lifecycle_version) == ("NEW", "INTAKE", 1)
        assert (
            await session.scalar(select(TaskMessage.body).where(TaskMessage.task_id == task_id))
        ) == "private source text"
    async with queries.read() as session:
        assert await session.scalar(text("SHOW transaction_read_only")) == "on"


async def test_empty_windows_skip_unused_reads_and_preserve_global_cursor(
    activity_tasks, activity_sql
):
    factory, _, task_id, other_id = activity_tasks
    async with factory() as session:
        session.add(
            TaskEvent(task_id=other_id, source="user", event_type="TASK_CREATED", payload={})
        )
        await session.commit()
    await ActivityProjector(factory).project()
    queries = SqlActivityQueries(factory, 100, 20)
    flight = await queries.preflight(window(task_id))
    assert (flight["estimated_events"], flight["tasks"], flight["file_changes"]) == (0, 0, 0)
    activity_sql.clear()
    page = await queries.events(window(task_id), 0, flight["through_sequence"], 100)
    assert page == {"events": [], "next_sequence": flight["through_sequence"], "has_more": False}
    assert len(activity_sql) == 2  # Scope check and event page, without an empty file lookup.
    activity_sql.clear()
    assert await queries.baseline(window(task_id), flight["through_sequence"]) == {"tasks": []}
    assert len(activity_sql) == 2  # No baseline payload/task reads when the window is empty.


async def test_baseline_uses_history_not_current_task_state_and_bounds_queries(activity_tasks):
    factory, _, task_id, _ = activity_tasks
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                TaskEvent(
                    task_id=task_id,
                    source="engineering",
                    event_type="TASK_LIFECYCLE_CHANGED",
                    created_at=now - timedelta(days=2),
                    payload={
                        "to_status": "WAITING_HUMAN",
                        "to_stage": "REVIEWING",
                        "wait_reason": "APPROVAL_REQUIRED",
                        "version": 3,
                    },
                ),
                TaskEvent(
                    task_id=task_id,
                    source="user",
                    event_type="HUMAN_INPUT_RESOLVED",
                    created_at=now - timedelta(hours=1),
                    payload={},
                ),
            ]
        )
        await session.commit()
    await ActivityProjector(factory).project()
    queries = SqlActivityQueries(factory, 100, 20)
    flight = await queries.preflight(window(task_id))
    baseline = await queries.baseline(window(task_id), flight["through_sequence"])
    assert baseline["tasks"][0]["status"] == "WAITING_HUMAN"
    assert baseline["tasks"][0]["stage"] == "REVIEWING"
    assert flight["estimated_events"] == 1
    narrow = SqlActivityQueries(factory, 1, 20)
    assert (await narrow.preflight(window(task_id, now - timedelta(days=3))))["too_large"]
    with pytest.raises(LookupError):
        await queries.preflight(window(uuid4()))


async def test_projection_failure_cannot_block_a_normal_lifecycle_transition(
    activity_tasks, monkeypatch
):
    factory, _, task_id, _ = activity_tasks
    projector = ActivityProjector(factory)
    monkeypatch.setattr(
        projector, "messages", AsyncMock(side_effect=RuntimeError("projection unavailable"))
    )
    with pytest.raises(RuntimeError):
        await projector.project()
    async with factory() as session:
        result = await record_transition(
            session, task_id, Action.START, expected_version=1, actor="test"
        )
        await session.commit()
        assert result.status.value == "ACTIVE"
    async with factory() as session:
        assert not list(
            await session.scalars(select(ActivityEvent).where(ActivityEvent.task_id == task_id))
        )


async def test_file_metadata_is_atomic_idempotent_and_scoped(activity_tasks, monkeypatch, tmp_path):
    factory, _, task_id, _ = activity_tasks
    repository_id = uuid4()
    try:
        async with factory() as session:
            session.add(
                Repository(
                    id=repository_id,
                    owner="local",
                    name="test",
                    external_repo_id=str(repository_id),
                    clone_url="https://example.test/repo",
                )
            )
            await session.flush()
            task = await session.get(Task, task_id)
            task.repository_id = repository_id
            task.workspace_path = str(tmp_path)
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="engineering",
                    event_type="VALIDATION_BATCH_COMPLETED",
                    payload={"passed": True, "head_sha": "a" * 40},
                )
            )
            await session.commit()
        await ActivityProjector(factory).project()
        files = [
            {
                "operation": "R",
                "path": "new.py",
                "previous_path": "old.py",
                "lines_added": 1,
                "lines_deleted": 0,
            }
        ]
        collector = AsyncMock(return_value=files)
        monkeypatch.setattr("app.activity.infrastructure.files.committed_changes", collector)
        await collect_files(factory, tmp_path)
        await collect_files(factory, tmp_path)
        collector.assert_awaited_once()
        queries = SqlActivityQueries(factory, 100, 20)
        scope = ActivityWindow(
            ActivityScope("repository", str(repository_id)),
            datetime.now(UTC) - timedelta(days=1),
            datetime.now(UTC),
        )
        page = await queries.events(scope, 0, None, 100)
        code = [event for event in page["events"] if event["kind"] == "CODE_CHANGED"]
        assert len(code) == 1
        assert code[0]["files"] == [{"repository_id": str(repository_id), **files[0]}]
        assert (await queries.preflight(scope))["file_changes"] == 1
        async with factory() as session:
            assert (
                len(
                    list(
                        await session.scalars(
                            select(ActivityFileChange).where(
                                ActivityFileChange.repository_id == repository_id
                            )
                        )
                    )
                )
                == 1
            )
    finally:
        async with factory() as session:
            task = await session.get(Task, task_id)
            task.repository_id = None
            await session.flush()
            await session.execute(delete(Repository).where(Repository.id == repository_id))
            await session.commit()


async def test_recorded_coordinator_causes_resolve_without_exposing_context(activity_tasks):
    from app.coordinator.infrastructure.models import (
        CoordinatorAction,
        CoordinatorEvent,
        CoordinatorRun,
    )

    factory, _, task_id, _ = activity_tasks
    run_id, trigger_id, action_id = uuid4(), uuid4(), uuid4()
    async with factory() as session:
        session.add(
            CoordinatorRun(
                id=run_id,
                task_id=task_id,
                mode="ACTIVE",
                requirement_revision=1,
                lifecycle_revision=1,
                evidence={"event_id": str(trigger_id), "packet": "private packet"},
            )
        )
        await session.flush()
        session.add_all(
            [
                CoordinatorEvent(
                    id=trigger_id,
                    task_id=task_id,
                    provider="github",
                    delivery_key=str(trigger_id),
                    kind="REVIEW",
                    actor="Reviewer",
                    context={"body": "private feedback"},
                ),
                CoordinatorAction(
                    id=action_id,
                    run_id=run_id,
                    task_id=task_id,
                    kind="REQUEST_DEVELOPMENT",
                    arguments={"instructions": "private instructions"},
                ),
                TaskEvent(
                    task_id=task_id,
                    source="coordinator",
                    event_type="COORDINATOR_STARTED",
                    payload={"run_id": str(run_id)},
                ),
                TaskEvent(
                    task_id=task_id,
                    source="coordinator",
                    event_type="COORDINATOR_DECIDED",
                    payload={"run_id": str(run_id)},
                ),
                TaskEvent(
                    task_id=task_id,
                    source="coordinator",
                    event_type="ACTION_EXECUTED",
                    payload={"action_id": str(action_id)},
                ),
            ]
        )
        await session.commit()
    await ActivityProjector(factory).project()
    queries = SqlActivityQueries(factory, 100, 20)
    flight = await queries.preflight(window(task_id))
    page = await queries.events(window(task_id), 0, flight["through_sequence"], 100)
    by_kind = {event["kind"]: event for event in page["events"]}
    for child, parent in [
        ("COORDINATOR_STARTED", "COORDINATION_INPUT_RECEIVED"),
        ("COORDINATOR_DECIDED", "COORDINATOR_STARTED"),
        ("ACTION_EXECUTED", "COORDINATOR_DECIDED"),
    ]:
        assert [item["kind"] for item in by_kind[child]["parents"]] == [parent]
    inspector = await queries.inspect(
        window(task_id), by_kind["COORDINATOR_DECIDED"]["sequence"], flight["through_sequence"]
    )
    assert [item["kind"] for item in inspector["children"]] == ["ACTION_EXECUTED"]
    assert "private" not in str(page) and "private" not in str(inspector)
    assert inspector["event"]["unresolved_parents"] == 0


async def test_inspector_is_scoped_fenced_and_separates_revision_checks(activity_tasks):
    from app.activity.domain.events import reference

    factory, _, task_id, other_id = activity_tasks
    now = datetime.now(UTC)

    def activity(task, identity, kind, **kwargs):
        return ActivityEvent(
            task_id=task,
            source_type="test",
            source_id=identity,
            kind=kind,
            occurred_at=now,
            actor_type="system",
            actor="Validator",
            **kwargs,
        )

    async with factory() as session:
        parent = activity(
            task_id,
            str(uuid4()),
            "VALIDATION_FAILED",
            payload={"head_sha": "a" * 40, "requirement_version": 1},
        )
        session.add(parent)
        await session.flush()
        session.add_all(
            [
                activity(
                    task_id,
                    str(uuid4()),
                    "VALIDATION_CHECK_COMPLETED",
                    payload={
                        "head_sha": "a" * 40,
                        "requirement_version": 1,
                        "check_kind": "tests",
                        "status": "FAILED",
                    },
                ),
                activity(
                    task_id,
                    str(uuid4()),
                    "VALIDATION_CHECK_COMPLETED",
                    payload={"head_sha": "a" * 40, "requirement_version": 2},
                ),
                activity(
                    other_id,
                    str(uuid4()),
                    "PRIVATE_OTHER_TASK",
                    references=[reference("test", parent.source_id, "triggered_by")],
                ),
            ]
        )
        await session.commit()
    queries = SqlActivityQueries(factory, 100, 20)
    through = (await queries.preflight(window(task_id)))["through_sequence"]
    async with factory() as session:
        session.add(
            activity(
                task_id,
                str(uuid4()),
                "LATE_CHILD",
                references=[reference("test", parent.source_id, "triggered_by")],
            )
        )
        await session.commit()
    inspected = await queries.inspect(window(task_id), parent.sequence, through)
    assert not inspected["children"]
    assert len(inspected["checks"]) == 1
    assert inspected["checks"][0]["payload"]["check_kind"] == "tests"
    with pytest.raises(LookupError):
        await queries.inspect(window(other_id), parent.sequence, through)
    summary = await queries.aggregate(window(task_id), through)
    assert summary["events"] == 3
    assert len(summary["buckets"]) == 1
    assert summary["buckets"][0]["validation_failed"] == 1
    assert summary["buckets"][0]["tasks"] == 1


async def test_file_retention_keeps_milestones_and_prevents_recollection(activity_tasks, tmp_path):
    from app.activity.infrastructure.retention import expire_file_details

    factory, _, task_id, _ = activity_tasks
    repository_id = uuid4()
    try:
        async with factory() as session:
            session.add(
                Repository(
                    id=repository_id,
                    owner="local",
                    name="retention",
                    external_repo_id=str(repository_id),
                    clone_url="https://example.test/repo",
                )
            )
            await session.flush()
            code = ActivityEvent(
                task_id=task_id,
                source_type="code",
                source_id=f"{task_id}:{'a' * 40}",
                kind="CODE_CHANGED",
                occurred_at=datetime.now(UTC) - timedelta(days=10),
                actor_type="system",
                actor="Commit",
                file_status="COMPLETE",
                payload={"head_sha": "a" * 40, "file_count": 1, "lines_added": 3},
            )
            session.add(code)
            await session.flush()
            session.add(
                ActivityFileChange(
                    event_sequence=code.sequence,
                    repository_id=repository_id,
                    operation="A",
                    path="src/a.py",
                    lines_added=3,
                    lines_deleted=0,
                )
            )
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="engineering",
                    event_type="VALIDATION_BATCH_COMPLETED",
                    payload={"passed": True, "head_sha": "a" * 40},
                )
            )
            await session.commit()
        assert await expire_file_details(factory, 0) == 0
        assert await expire_file_details(factory, 5) == 1
        assert await expire_file_details(factory, 5) == 0
        await ActivityProjector(factory).project()
        await collect_files(factory, tmp_path)
        queries = SqlActivityQueries(factory, 100, 20)
        page = await queries.events(
            window(task_id, datetime.now(UTC) - timedelta(days=15)), 0, None, 100
        )
        retained = next(event for event in page["events"] if event["kind"] == "CODE_CHANGED")
        assert retained["file_status"] == "EXPIRED" and retained["files"] == []
        assert retained["payload"]["lines_added"] == 3
        assert (await queries.preflight(window(task_id)))["file_history"]["counts"] == {
            "EXPIRED": 1
        }
        async with factory() as session:
            assert (
                await session.scalar(select(TaskEvent.id).where(TaskEvent.task_id == task_id))
                is not None
            )
    finally:
        async with factory() as session:
            await session.execute(delete(Repository).where(Repository.id == repository_id))
            await session.commit()


async def test_capacity_uses_historical_limits_and_all_tasks_in_the_visible_team(activity_tasks):
    from app.engineering.infrastructure.task_models import Job
    from app.platform.scheduling.states import JobState
    from app.teams.infrastructure.team_models import TeamCapacityChange

    factory, team_id, task_id, other_id = activity_tasks
    now = datetime.now(UTC)
    async with factory() as session:
        other = await session.get(Task, other_id)
        other.team_id = team_id
        session.add_all(
            [
                TeamCapacityChange(
                    team_id=team_id, capacity=1, created_at=now - timedelta(seconds=30)
                ),
                TeamCapacityChange(
                    team_id=team_id, capacity=2, created_at=now - timedelta(seconds=10)
                ),
                TaskEvent(
                    task_id=task_id, source="engineering", event_type="TASK_CREATED", payload={}
                ),
            ]
        )
        for id in (task_id, other_id):
            session.add(
                Job(
                    task_id=id,
                    action="DEVELOPER_TURN",
                    state=JobState.SUCCEEDED,
                    attempt=1,
                    started_at=now - timedelta(seconds=20),
                    finished_at=now - timedelta(seconds=5),
                )
            )
        await session.commit()
    await ActivityProjector(factory).project()
    flight = await SqlActivityQueries(factory, 100, 20).preflight(window(task_id))
    evidence = flight["capacity"]
    assert evidence["truncated"] is False
    assert len(evidence["teams"]) == 1
    team = evidence["teams"][0]
    assert [item["capacity"] for item in team["limits"]] == [1, 2]
    assert {item["task_id"] for item in team["jobs"]} == {str(task_id), str(other_id)}
    assert all(item["complete"] and item["end"] for item in team["jobs"])


async def test_plan_audit_deduplicates_snapshots_and_projects_only_public_graph_facts(
    activity_tasks,
):
    from app.agent_runtime.infrastructure.work_history import record_work_history

    factory, _, task_id, _ = activity_tasks
    plans = [
        {
            "revision": 0,
            "units": [
                {
                    "id": "schema",
                    "status": "READY",
                    "depends_on": [],
                    "objective": "private source",
                },
                {"id": "api", "status": "RUNNING", "depends_on": [0]},
            ],
        }
    ]
    async with factory() as session:
        run = AIRun(
            task_id=task_id,
            provider="test",
            model="model",
            role_kind="DEVELOPER",
            prompt_version="test",
            status="RUNNING",
        )
        session.add(run)
        await session.flush()
        snapshot = {"work_plans": plans, "private_context": "private source"}
        record_work_history(session, run, snapshot)
        run.token_efficiency = snapshot
        record_work_history(session, run, snapshot)
        await session.commit()
    await ActivityProjector(factory).project()
    page = await SqlActivityQueries(factory, 100, 20).events(window(task_id), 0, None, 100)
    snapshots = [event for event in page["events"] if event["kind"] == "WORK_PLAN_UPDATED"]
    assert len(snapshots) == 1
    assert snapshots[0]["payload"]["work_plans"][0]["units"][1]["depends_on"] == [0]
    assert snapshots[0]["parents"][0]["kind"] == "AI_RUN_STARTED"
    assert "private" not in str(snapshots)


async def test_review_repair_transition_and_job_keep_explicit_source_links(activity_tasks):
    from app.engineering.domain.causality import TransitionCause
    from app.engineering.infrastructure.jobs import enqueue_phase
    from app.platform.scheduling.states import JobState

    factory, _, task_id, _ = activity_tasks
    async with factory() as session:
        task = await session.get(Task, task_id)
        task.status, task.stage = "WAITING_EXTERNAL", "REVIEWING"
        task.wait_reason = "GITHUB_REVIEW"
        review = ReviewCycle(
            task_id=task_id,
            external_event_id="causal-review",
            head_sha="a" * 40,
            actor="Reviewer",
            decision="CHANGES_REQUESTED",
            feedback={},
        )
        session.add(review)
        await session.flush()
        await record_transition(
            session,
            task_id,
            Action.REVIEW_FIX,
            expected_version=task.lifecycle_version,
            actor="reviewer",
            cause=TransitionCause(review_ids=(review.id,)),
        )
        job = await enqueue_phase(session, task)
        assert job is not None
        job.state, job.attempt, job.started_at = JobState.RUNNING, 1, datetime.now(UTC)
        await session.commit()
    await ActivityProjector(factory).project()
    page = await SqlActivityQueries(factory, 100, 20).events(window(task_id), 0, None, 100)
    kinds = {event["kind"]: event for event in page["events"]}
    assert kinds["TASK_STATE_CHANGED"]["parents"][0]["kind"] == "REVIEW_RECEIVED"
    assert kinds["JOB_QUEUED"]["parents"][0]["kind"] == "TASK_STATE_CHANGED"
    assert kinds["JOB_STARTED"]["parents"][0]["kind"] == "JOB_QUEUED"
