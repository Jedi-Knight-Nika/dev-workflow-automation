import asyncio
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.reviewer_completion import ReviewerCompletionContext
from app.db.models import (
    Job,
    JobRole,
    JobState,
    Task,
    TaskEvent,
    TaskState,
    Team,
    WorkflowDefinition,
    WorkflowNode,
)
from app.domain.jobs import CompletionDirective
from app.infrastructure.persistence.job_operations import claim_next_job
from app.infrastructure.persistence.reviewer_completion import (
    SqlAlchemyReviewerCompletionUnitOfWork,
)

pytestmark = pytest.mark.asyncio


async def _delete_test_team(
    session_factory: async_sessionmaker[AsyncSession], team_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        task_ids = select(Task.id).where(Task.team_id == team_id)
        await session.execute(delete(Task).where(Task.id.in_(task_ids)))
        await session.execute(delete(Team).where(Team.id == team_id))
        await session.commit()


async def test_concurrent_claims_respect_team_limit(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id = uuid.uuid4()
    task_ids = [uuid.uuid4(), uuid.uuid4()]
    try:
        async with postgres_session_factory() as session:
            session.add(
                Team(
                    id=team_id,
                    name=f"claim-test-{team_id}",
                    max_concurrent_tasks=1,
                )
            )
            await session.flush()
            for task_id in task_ids:
                session.add(Task(id=task_id, title=f"Concurrent claim {task_id}", team_id=team_id))
                await session.flush()
                session.add(
                    Job(
                        task_id=task_id,
                        role=JobRole.EXECUTOR,
                        action="IMPLEMENT",
                        state=JobState.QUEUED,
                    )
                )
            await session.commit()

        first = postgres_session_factory()
        second = postgres_session_factory()
        try:
            claims = await asyncio.gather(
                claim_next_job(first, "integration-worker-1", 60),
                claim_next_job(second, "integration-worker-2", 60),
            )
        finally:
            await first.close()
            await second.close()

        claimed = [job for job in claims if job is not None]
        assert len(claimed) == 1
        assert claimed[0].task_id in task_ids
    finally:
        await _delete_test_team(postgres_session_factory, team_id)


async def test_review_cycle_limit_routes_task_to_human_attention(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    team_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    node_id = uuid.uuid4()
    task_id = uuid.uuid4()
    review_job_id = uuid.uuid4()
    try:
        async with postgres_session_factory() as session:
            session.add(Team(id=team_id, name=f"review-limit-test-{team_id}"))
            await session.flush()
            session.add(
                WorkflowDefinition(
                    id=workflow_id,
                    team_id=team_id,
                    name="Review limit integration workflow",
                )
            )
            await session.flush()
            session.add(
                WorkflowNode(
                    id=node_id,
                    workflow_id=workflow_id,
                    role=JobRole.REVIEWER.value,
                    label="Reviewer",
                    position_x=0,
                    position_y=0,
                    max_review_cycles=1,
                )
            )
            await session.flush()
            session.add(
                Task(
                    id=task_id,
                    title="Bound the review loop",
                    team_id=team_id,
                    workflow_id=workflow_id,
                    workflow_version=1,
                    state=TaskState.INTERNAL_REVIEW,
                )
            )
            await session.flush()
            session.add(
                Job(
                    id=review_job_id,
                    task_id=task_id,
                    workflow_node_id=node_id,
                    role=JobRole.REVIEWER,
                    action="REVIEW_CHANGES",
                    state=JobState.SUCCEEDED,
                    result={"result": "FAIL_ACTIONABLE"},
                )
            )
            await session.commit()

        context = ReviewerCompletionContext(
            review_job_id,
            task_id,
            "REVIEW_CHANGES",
            "FAIL_ACTIONABLE",
            {},
            {"result": "FAIL_ACTIONABLE"},
            0,
            False,
        )
        unit = SqlAlchemyReviewerCompletionUnitOfWork(postgres_session_factory, 5, 3, 2)
        async with unit:
            await unit.apply(context, CompletionDirective.REVIEW_REPAIR)
            await unit.commit()

        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            repair_jobs = await session.scalars(
                select(Job).where(Job.task_id == task_id, Job.role == JobRole.EXECUTOR)
            )
            event_types = set(
                await session.scalars(
                    select(TaskEvent.event_type).where(TaskEvent.task_id == task_id)
                )
            )
            assert task is not None and task.state == TaskState.NEEDS_HUMAN
            assert list(repair_jobs) == []
            assert "REVIEW_CYCLE_LIMIT_REACHED" in event_types
    finally:
        await _delete_test_team(postgres_session_factory, team_id)
