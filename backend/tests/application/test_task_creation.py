from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.engineering.application.create_task import CreateTask, CreateTaskCommand
from app.engineering.domain.task import Task


@pytest.mark.asyncio
async def test_selected_team_is_assigned_before_start_and_committed_once():
    unit = AsyncMock()
    unit.tasks.find_creation.return_value = None
    order = []
    unit.assignments.assign.side_effect = lambda *args: order.append("assign")
    unit.execution.start.side_effect = lambda *args, **kwargs: order.append("start")
    command = CreateTaskCommand(
        title="Create", team_id=uuid4(), request_id=uuid4(), start_work=True
    )
    task = await CreateTask(unit).execute(command)
    assert order == ["assign", "start"]
    assert task.team_id == command.team_id
    unit.commit.assert_awaited_once()
    unit.tasks.remember_creation.assert_awaited_once()


@pytest.mark.asyncio
async def test_creation_replay_does_not_assign_or_start_again():
    unit = AsyncMock()
    existing = Task.create(title="Existing")
    unit.tasks.find_creation.return_value = existing
    result = await CreateTask(unit).execute(
        CreateTaskCommand(title="Existing", request_id=uuid4(), start_work=True)
    )
    assert result is existing
    unit.tasks.add.assert_not_awaited()
    unit.assignments.assign.assert_not_awaited()
    unit.execution.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_assignment_failure_rolls_back_creation_without_starting():
    unit = AsyncMock()
    unit.assignments.assign.side_effect = ValueError("Team scope changed")
    with pytest.raises(ValueError, match="Team scope changed"):
        await CreateTask(unit).execute(
            CreateTaskCommand(title="Create", team_id=uuid4(), start_work=True)
        )
    unit.rollback.assert_awaited_once()
    unit.commit.assert_not_awaited()
    unit.execution.start.assert_not_awaited()
