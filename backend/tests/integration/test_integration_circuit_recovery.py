import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    FailureEvent,
    HealthState,
    Integration,
    IntegrationStatus,
    Job,
    JobRole,
    JobState,
    Task,
    Team,
    WorkflowDefinition,
    WorkflowNode,
)
from app.infrastructure.persistence.job_operations import claim_next_job
from app.infrastructure.persistence.resilience import SqlAlchemyResilienceStore

pytestmark = pytest.mark.asyncio


async def _delete_test_team(
    session_factory: async_sessionmaker[AsyncSession], team_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        task_ids = select(Task.id).where(Task.team_id == team_id)
        await session.execute(delete(Task).where(Task.id.in_(task_ids)))
        await session.execute(delete(Team).where(Team.id == team_id))
        await session.commit()


async def test_open_integration_circuit_blocks_only_dependent_workflow_job(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    blocked_node_id = uuid.uuid4()
    runnable_node_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    health_id = uuid.uuid4()
    try:
        async with postgres_session_factory() as session:
            session.add(Team(id=team_id, name=f"integration-circuit-{team_id}"))
            session.add(
                Integration(
                    id=integration_id,
                    provider_type="TASK_MANAGEMENT",
                    provider_name=f"linear-{integration_id}",
                    status=IntegrationStatus.CONNECTED,
                )
            )
            await session.flush()
            session.add(
                WorkflowDefinition(id=workflow_id, team_id=team_id, name="Circuit workflow")
            )
            await session.flush()
            session.add_all(
                [
                    WorkflowNode(
                        id=blocked_node_id,
                        workflow_id=workflow_id,
                        role=JobRole.INTAKE.value,
                        label="Blocked intake",
                        position_x=0,
                        position_y=0,
                        integration_ids=[str(integration_id)],
                    ),
                    WorkflowNode(
                        id=runnable_node_id,
                        workflow_id=workflow_id,
                        role=JobRole.THINKER.value,
                        label="Independent thinker",
                        position_x=100,
                        position_y=0,
                    ),
                ]
            )
            session.add(
                HealthState(
                    id=health_id,
                    resource_type="INTEGRATION",
                    resource_id=f"linear-{integration_id}",
                    status="UNAVAILABLE",
                    circuit_state="OPEN",
                    consecutive_failures=3,
                    next_probe_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            )
            for index, node_id in enumerate((blocked_node_id, runnable_node_id)):
                task = Task(title=f"Circuit task {index}", team_id=team_id, workflow_id=workflow_id)
                session.add(task)
                await session.flush()
                session.add(
                    Job(
                        task_id=task.id,
                        workflow_node_id=node_id,
                        role=JobRole.INTAKE if index == 0 else JobRole.THINKER,
                        action="WORK",
                        state=JobState.QUEUED,
                        priority=index,
                    )
                )
            await session.commit()

        async with postgres_session_factory() as session:
            claimed = await claim_next_job(session, "integration-worker", 60)
            assert claimed is not None
            assert claimed.workflow_node_id == runnable_node_id
    finally:
        await _delete_test_team(postgres_session_factory, team_id)
        async with postgres_session_factory() as session:
            await session.execute(delete(HealthState).where(HealthState.id == health_id))
            await session.execute(delete(Integration).where(Integration.id == integration_id))
            await session.commit()


async def test_due_integration_circuit_requeues_one_linked_waiting_job(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id = uuid.uuid4()
    task_id = uuid.uuid4()
    job_id = uuid.uuid4()
    health_id = uuid.uuid4()
    resource_id = f"github-{uuid.uuid4()}"
    try:
        async with postgres_session_factory() as session:
            session.add(Team(id=team_id, name=f"recovery-test-{team_id}"))
            await session.flush()
            session.add(Task(id=task_id, title="Recover integration", team_id=team_id))
            await session.flush()
            session.add(
                Job(
                    id=job_id,
                    task_id=task_id,
                    role=JobRole.EXECUTOR,
                    action="DELIVER",
                    state=JobState.WAITING_INTEGRATION,
                )
            )
            await session.flush()
            session.add(
                HealthState(
                    id=health_id,
                    resource_type="INTEGRATION",
                    resource_id=resource_id,
                    status="UNAVAILABLE",
                    circuit_state="OPEN",
                    consecutive_failures=3,
                    next_probe_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
            session.add(
                FailureEvent(
                    task_id=task_id,
                    job_id=job_id,
                    resource_type="INTEGRATION",
                    resource_id=resource_id,
                    failure_class="GITHUB_UNAVAILABLE",
                    fingerprint=f"github:{resource_id}",
                    safe_message="GitHub is unavailable",
                    retryable=True,
                )
            )
            await session.commit()

        recovered = await SqlAlchemyResilienceStore(postgres_session_factory).recover_due_resources(
            limit=1
        )

        async with postgres_session_factory() as session:
            job = await session.get(Job, job_id)
            health = await session.get(HealthState, health_id)
            assert recovered == 1
            assert job is not None and job.state == JobState.QUEUED
            assert health is not None and health.circuit_state == "HALF_OPEN"
            assert health.probe_job_id == job_id
    finally:
        await _delete_test_team(postgres_session_factory, team_id)
        async with postgres_session_factory() as session:
            await session.execute(delete(HealthState).where(HealthState.id == health_id))
            await session.commit()
