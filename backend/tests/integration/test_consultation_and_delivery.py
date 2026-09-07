import importlib.util
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.merge_workflow import MergeOutcome
from app.db.base import Base
from app.db.models import (
    AIAgent,
    Job,
    JobRole,
    JobState,
    Repository,
    Role,
    Task,
    TaskEvent,
    TaskMessage,
    TaskRepositoryScope,
    TaskState,
    Team,
    ValidationRecord,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)
from app.infrastructure.github_events import evaluate_current_revision
from app.infrastructure.persistence.consultations import SqlAlchemyConsultationStore
from app.infrastructure.persistence.workflow_routing import route_completed_job
from app.infrastructure.pull_requests.merge_workflow import SqlAlchemyGitHubMergeWorkflow
from app.worker import resolve_agent_config

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def isolated_sessions(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # All test tables live in a transaction-local schema. No real task or worker
    # can discover these queued jobs; rollback removes the entire test schema.
    async with postgres_session_factory() as owner:
        connection = await owner.connection()
        schema = "test_consult_" + uuid.uuid4().hex
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=False))
        try:
            yield async_sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
        finally:
            await owner.rollback()


async def seed_consultation(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    async with sessions() as session:
        team = Team(name="Consultation test")
        role = Role(name="Specialist", category="SPECIALIST", enabled=True)
        session.add_all([team, role])
        await session.flush()
        agents = [
            AIAgent(team_id=team.id, role_id=role.id, name=name) for name in ("Writer", "Planner")
        ]
        session.add_all(agents)
        await session.flush()
        graph = WorkflowDefinition(id=uuid.uuid4(), team_id=team.id, version=1)
        session.add(graph)
        await session.flush()
        nodes = [
            WorkflowNode(
                id=uuid.uuid4(),
                workflow_id=graph.id,
                agent_id=agent.id,
                role=role_name,
                label=agent.name,
                position_x=0,
                position_y=0,
            )
            for agent, role_name in zip(agents, ("EXECUTOR", "THINKER"), strict=True)
        ]
        session.add_all(nodes)
        await session.flush()
        session.add(
            WorkflowEdge(
                id=uuid.uuid4(),
                workflow_id=graph.id,
                source_node_id=nodes[0].id,
                target_node_id=nodes[1].id,
                outcome="consultation",
                configuration={"kind": "consultation"},
            )
        )
        task = Task(
            title="Consult without restarting",
            team_id=team.id,
            workflow_id=graph.id,
            workflow_version=1,
            state=TaskState.IMPLEMENTING,
        )
        session.add(task)
        await session.flush()
        lease = uuid.uuid4()
        job = Job(
            task_id=task.id,
            agent_id=agents[0].id,
            workflow_node_id=nodes[0].id,
            team_workflow_version=1,
            role=JobRole.EXECUTOR,
            action="IMPLEMENT_PLAN",
            state=JobState.RUNNING,
            lease_token=lease,
        )
        session.add(job)
        await session.commit()
        return task.id, job.id, lease, nodes[1].id


async def test_question_reply_continuation_is_durable_and_idempotent(
    isolated_sessions: async_sessionmaker[AsyncSession],
) -> None:
    task_id, job_id, lease, target = await seed_consultation(isolated_sessions)
    store = SqlAlchemyConsultationStore(isolated_sessions)
    request = {
        "result": "CONSULTATION_REQUESTED",
        "data": {"target_node_id": str(target), "question": "Which invariant applies?"},
    }
    assert not await store.complete(job_id, uuid.uuid4(), request)
    assert await store.complete(job_id, lease, request)
    assert not await store.complete(job_id, lease, request)
    async with isolated_sessions() as session:
        task = await session.get(Task, task_id)
        assert task and task.state == TaskState.IMPLEMENTING
        reply_job = await session.scalar(select(Job).where(Job.action == "CONSULT_AGENT"))
        assert reply_job and reply_job.workflow_node_id == target
        reply_job.state = JobState.RUNNING
        reply_job.lease_token = uuid.uuid4()
        reply_id, reply_lease = reply_job.id, reply_job.lease_token
        await session.commit()
    assert await store.complete(
        reply_id,
        reply_lease,
        {"result": "CONSULTATION_REPLIED", "summary": "Preserve historical amounts."},
    )
    assert not await store.complete(
        reply_id, reply_lease, {"result": "CONSULTATION_REPLIED", "summary": "Duplicate"}
    )
    async with isolated_sessions() as session:
        jobs = list((await session.scalars(select(Job).where(Job.state == JobState.QUEUED))).all())
        assert len(jobs) == 1 and jobs[0].action == "IMPLEMENT_PLAN"
        assert jobs[0].payload["consultation_reply"]["answer"] == "Preserve historical amounts."
        messages = list((await session.scalars(select(TaskMessage).order_by(TaskMessage.id))).all())
        assert len(messages) == 2 and messages[1].reply_to_id == messages[0].id
        assert messages[0].context["status"] == "ANSWERED"
        assert (await session.get(Task, task_id)).state == TaskState.IMPLEMENTING


async def test_removed_consultation_route_blocks_once_instead_of_replaying(
    isolated_sessions: async_sessionmaker[AsyncSession],
) -> None:
    task_id, job_id, lease, _target = await seed_consultation(isolated_sessions)
    store = SqlAlchemyConsultationStore(isolated_sessions)
    result = {
        "result": "CONSULTATION_REQUESTED",
        "data": {"target_node_id": str(uuid.uuid4()), "question": "Unavailable?"},
    }
    assert await store.complete(job_id, lease, result)
    assert not await store.complete(job_id, lease, result)
    async with isolated_sessions() as session:
        job = await session.get(Job, job_id)
        task = await session.get(Task, task_id)
        assert job and job.state == JobState.WAITING_HUMAN
        assert task and task.state == TaskState.NEEDS_HUMAN


async def test_runtime_uses_pinned_node_when_two_agents_share_a_role(
    isolated_sessions: async_sessionmaker[AsyncSession],
) -> None:
    task_id, _job_id, _lease, target = await seed_consultation(isolated_sessions)
    async with isolated_sessions() as session:
        task = await session.get(Task, task_id)
        target_node = await session.get(WorkflowNode, target)
        assert task and target_node
        nodes = list((await session.scalars(select(WorkflowNode))).all())
        for node in nodes:
            node.role = "EXECUTOR"
            node.model = "gpt-5.4"
        role = await session.scalar(select(Role))
        assert role
        role.capabilities = ["CAN_IMPLEMENT"]
        role.permissions = ["READ_REPOSITORY", "WRITE_REPOSITORY"]
        await session.flush()
        config = await resolve_agent_config(session, task, JobRole.EXECUTOR, target)
        assert config and config.agent_id == target_node.agent_id
        assert await resolve_agent_config(session, task, JobRole.EXECUTOR, uuid.uuid4()) is None


async def test_last_validation_gate_delivers_without_restarting_intake(
    isolated_sessions: async_sessionmaker[AsyncSession],
) -> None:
    task_id, job_id, _lease, target_id = await seed_consultation(isolated_sessions)
    async with isolated_sessions() as session:
        task = await session.get(Task, task_id)
        job = await session.get(Job, job_id)
        target = await session.get(WorkflowNode, target_id)
        assert task and job and target
        job.role = JobRole.TESTER
        target.role = "DELIVERER"
        session.add(
            WorkflowEdge(
                id=uuid.uuid4(),
                workflow_id=target.workflow_id,
                source_node_id=job.workflow_node_id,
                target_node_id=target.id,
                outcome="success",
            )
        )
        await session.flush()
        result = await route_completed_job(session, task, job.id, "TEST_PASS", {})
        assert result and result.publish
        assert task.state == TaskState.WAITING_GITHUB
        assert not list(
            (await session.scalars(select(Job).where(Job.state == JobState.QUEUED))).all()
        )


async def test_multi_repo_merges_require_each_scope_and_fresh_approval(
    isolated_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with isolated_sessions() as session:
        repositories = [
            Repository(
                owner="test",
                name=name,
                external_repo_id=name,
                clone_url=f"https://example.test/{name}.git",
                default_branch="main",
            )
            for name in ("one", "two")
        ]
        session.add_all(repositories)
        await session.flush()
        task = Task(
            title="Two repositories",
            repository_id=repositories[0].id,
            current_revision="same-sha",
            pull_request_number=1,
            state=TaskState.WAITING_GITHUB,
        )
        session.add(task)
        await session.flush()
        scopes = [
            TaskRepositoryScope(
                task_id=task.id,
                repository_id=repo.id,
                is_primary=i == 0,
                changed=True,
                current_revision="same-sha",
                pull_request_number=i + 1,
            )
            for i, repo in enumerate(repositories)
        ]
        session.add_all(scopes)
        for repo in repositories:
            session.add(
                ValidationRecord(
                    task_id=task.id,
                    provider="github",
                    kind="CHECK",
                    name="CI",
                    status="SUCCESS",
                    revision="same-sha",
                    payload={"repository_id": str(repo.id)},
                )
            )
        session.add(
            TaskEvent(
                task_id=task.id,
                source="github",
                event_type="PULL_REQUEST_MERGE_REQUESTED",
                payload={"revision": "old-sha", "repository_id": str(repositories[1].id)},
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
        calls = []

        async def merge(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr("app.infrastructure.github_events.MergeTask.execute", merge)
        await evaluate_current_revision(session, task, scopes[1])
        assert not calls  # Old approval cannot authorize this revision.
        for repo in repositories:
            session.add(
                TaskEvent(
                    task_id=task.id,
                    source="github",
                    event_type="PULL_REQUEST_MERGE_REQUESTED",
                    payload={"revision": "same-sha", "repository_id": str(repo.id)},
                )
            )
        await session.flush()
        await evaluate_current_revision(session, task, scopes[0])
        assert (
            len(calls) == 1
        )  # A later approval for repository two cannot hide repository one's approval.
        workflow = SqlAlchemyGitHubMergeWorkflow(session, repositories[0].id)
        context = await workflow.load_context(task.id)
        assert context and len(context.evidence) == 1
        await workflow.complete(context, MergeOutcome(True, "merged-one", "Merged"))
        assert task.state == TaskState.WAITING_GITHUB and task.completed_at is None
        workflow = SqlAlchemyGitHubMergeWorkflow(session, repositories[1].id)
        context = await workflow.load_context(task.id)
        assert context and len(context.evidence) == 1
        await workflow.complete(context, MergeOutcome(True, "merged-two", "Merged"))
        assert task.state == TaskState.MERGED and task.completed_at is not None


async def test_combined_deliverer_migration_round_trip(
    isolated_sessions: async_sessionmaker[AsyncSession],
) -> None:
    task_id, job_id, _lease, old_delivery = await seed_consultation(isolated_sessions)
    async with isolated_sessions() as session:
        job = await session.get(Job, job_id)
        assert job
        incoming = await session.get(WorkflowNode, job.workflow_node_id)
        old = await session.get(WorkflowNode, old_delivery)
        assert incoming and old
        incoming.role, old.role = "INTAKE", "DELIVERER"
        job.role = JobRole.INTAKE
        role = await session.get(Role, (await session.get(AIAgent, incoming.agent_id)).role_id)
        assert role
        role.name, role.built_in = "Intake", True
        role.runtime_profile = {"reasoning_min": "LOW"}
        session.add(Role(name="Deliverer", category="DELIVERY", built_in=True))
        controller_id = uuid.uuid4()
        session.add(
            WorkflowNode(
                id=controller_id,
                workflow_id=incoming.workflow_id,
                role="ORCHESTRATOR",
                label="Dispatcher",
                position_x=0,
                position_y=0,
            )
        )
        await session.flush()
        edge = WorkflowEdge(
            id=uuid.uuid4(),
            workflow_id=incoming.workflow_id,
            source_node_id=old.id,
            target_node_id=controller_id,
            outcome="always",
        )
        session.add(edge)
        workflow_id, kept_id, edge_id = incoming.workflow_id, incoming.id, edge.id
        await session.commit()

    spec = importlib.util.spec_from_file_location(
        "combined_migration", Path("migrations/versions/0055_combined_deliverer.py")
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with isolated_sessions() as session:
        connection = await session.connection()

        def run(sync, direction):
            migration.op = Operations(MigrationContext.configure(sync))
            getattr(migration, direction)()

        await connection.run_sync(run, "upgrade")
        await session.commit()
    async with isolated_sessions() as session:
        assert (await session.get(WorkflowNode, kept_id)).role == "DELIVERER"
        assert await session.get(WorkflowNode, old_delivery) is None
        assert (await session.get(WorkflowEdge, edge_id)).source_node_id == kept_id
        assert (await session.get(WorkflowDefinition, workflow_id)).version == 2
        assert (await session.get(Job, job_id)).role == JobRole.DELIVERER
    async with isolated_sessions() as session:
        connection = await session.connection()
        await connection.run_sync(run, "downgrade")
        await connection.run_sync(run, "upgrade")
        await session.commit()
    async with isolated_sessions() as session:
        assert (await session.get(WorkflowNode, kept_id)).role == "DELIVERER"
        assert (await session.get(WorkflowDefinition, workflow_id)).version == 2
        assert (await session.get(Task, task_id)).workflow_version == 2
