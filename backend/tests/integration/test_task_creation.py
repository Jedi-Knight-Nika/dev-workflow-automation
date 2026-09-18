import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.engineering.application.create_task import CreateTask, CreateTaskCommand, CreationConflict
from app.engineering.infrastructure.task_models import Job, Task, TaskCreationRequest, TaskEvent
from app.engineering.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.teams.application.ports.team_management import TeamNotFound
from app.teams.infrastructure.team_models import TaskAssignment, Team


@pytest.mark.asyncio
async def test_concurrent_creation_retries_have_one_task_assignment_and_event(
    postgres_session_factory,
):
    team_id = uuid4()
    command = CreateTaskCommand(title="Atomic draft", team_id=team_id, request_id=uuid4())
    async with postgres_session_factory.begin() as session:
        session.add(Team(id=team_id, name=f"creation-{team_id}"))

    async def create():
        async with postgres_session_factory() as session:
            return await CreateTask(SqlAlchemyUnitOfWork(session)).execute(command)

    try:
        first, second = await asyncio.gather(create(), create())
        assert first.id == second.id
        assert first.team_id == second.team_id == team_id
        async with postgres_session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(TaskAssignment)
                    .where(TaskAssignment.task_id == first.id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == first.id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(Job).where(Job.task_id == first.id)
                )
                == 0
            )
            with pytest.raises(CreationConflict):
                await CreateTask(SqlAlchemyUnitOfWork(session)).execute(
                    replace(command, start_work=True)
                )
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.team_id == team_id))
            await session.execute(delete(Team).where(Team.id == team_id))


@pytest.mark.asyncio
async def test_assignment_failure_rolls_back_and_same_request_can_be_retried(
    postgres_session_factory,
):
    team_id = uuid4()
    command = CreateTaskCommand(
        title=f"rollback-{uuid4()}", team_id=team_id, request_id=uuid4(), start_work=True
    )
    async with postgres_session_factory() as session:
        with pytest.raises(TeamNotFound):
            await CreateTask(SqlAlchemyUnitOfWork(session)).execute(command)
        assert await session.scalar(select(Task.id).where(Task.title == command.title)) is None
        assert await session.get(TaskCreationRequest, command.request_id) is None
    async with postgres_session_factory.begin() as session:
        session.add(Team(id=team_id, name=f"creation-{team_id}"))
    try:
        async with postgres_session_factory() as session:
            task = await CreateTask(SqlAlchemyUnitOfWork(session)).execute(command)
            assert task.team_id == team_id
            assert task.status == "WAITING_HUMAN"
            assert task.wait_reason == "MISSING_CONFIGURATION"
            assert await session.scalar(select(Job.id).where(Job.task_id == task.id)) is None
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.team_id == team_id))
            await session.execute(delete(Team).where(Team.id == team_id))
