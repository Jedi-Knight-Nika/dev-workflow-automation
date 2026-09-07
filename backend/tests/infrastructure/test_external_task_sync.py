import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import ExternalTaskSnapshot, Integration, Task, TaskState
from app.infrastructure.external_task_sync import sync_external_task_state


@pytest.mark.asyncio
async def test_trello_task_state_moves_originating_card() -> None:
    task = Task(id=uuid.uuid4(), title="Work", state=TaskState.IMPLEMENTING)
    snapshot = ExternalTaskSnapshot(
        task_id=task.id,
        provider="trello",
        external_id="card-1",
        identifier="TRELLO-1",
        state_id="ready",
        raw_payload={"idList": "ready"},
    )
    integration = Integration(
        provider_name="trello",
        provider_type="task_management",
        configuration={"in_progress_list_id": "doing"},
        encrypted_credentials=b"encrypted",
    )
    session = AsyncMock()
    session.scalar.side_effect = [snapshot, integration, None]

    with (
        patch(
            "app.infrastructure.external_task_sync.cipher.decrypt",
            return_value='{"api_key":"key","token":"token"}',
        ),
        patch(
            "app.infrastructure.external_task_sync.TrelloClient.update_card_list",
            new=AsyncMock(),
        ) as update_card_list,
        patch(
            "app.infrastructure.external_task_sync.record_event", new=AsyncMock()
        ) as record_event,
    ):
        synced = await sync_external_task_state(session, task)

    assert synced is True
    update_card_list.assert_awaited_once_with("card-1", "doing")
    assert snapshot.state_id == "doing"
    assert snapshot.raw_payload["idList"] == "doing"
    record_event.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_trello_task_state_discovers_conventional_list_when_mapping_missing() -> None:
    task = Task(id=uuid.uuid4(), title="Work", state=TaskState.IMPLEMENTING)
    snapshot = ExternalTaskSnapshot(
        task_id=task.id,
        provider="trello",
        external_id="card-1",
        identifier="TRELLO-1",
        state_id="todo",
        raw_payload={"idList": "todo"},
    )
    integration = Integration(
        provider_name="trello",
        provider_type="task_management",
        configuration={"board_id": "board-1"},
        encrypted_credentials=b"encrypted",
    )
    session = AsyncMock()
    session.scalar.side_effect = [snapshot, integration, None]

    with (
        patch(
            "app.infrastructure.external_task_sync.cipher.decrypt",
            return_value='{"api_key":"key","token":"token"}',
        ),
        patch(
            "app.infrastructure.external_task_sync.TrelloClient.list_lists",
            new=AsyncMock(
                return_value=[
                    {"id": "doing", "name": "IN PROGRESS", "closed": False},
                    {"id": "done", "name": "DONE", "closed": False},
                ]
            ),
        ),
        patch(
            "app.infrastructure.external_task_sync.TrelloClient.update_card_list",
            new=AsyncMock(),
        ) as update_card_list,
        patch("app.infrastructure.external_task_sync.record_event", new=AsyncMock()),
    ):
        synced = await sync_external_task_state(session, task)

    assert synced is True
    assert integration.configuration["in_progress_list_id"] == "doing"
    update_card_list.assert_awaited_once_with("card-1", "doing")


@pytest.mark.asyncio
async def test_merged_trello_task_moves_to_done_not_testing() -> None:
    task = Task(id=uuid.uuid4(), title="Delivered", state=TaskState.MERGED)
    snapshot = ExternalTaskSnapshot(
        task_id=task.id,
        provider="trello",
        external_id="card-1",
        identifier="TRELLO-1",
        state_id="testing",
        raw_payload={"idList": "testing"},
    )
    integration = Integration(
        provider_name="trello",
        provider_type="task_management",
        configuration={"done_list_id": "done"},
        encrypted_credentials=b"encrypted",
    )
    session = AsyncMock()
    session.scalar.side_effect = [snapshot, integration, None]

    with (
        patch(
            "app.infrastructure.external_task_sync.cipher.decrypt",
            return_value='{"api_key":"key","token":"token"}',
        ),
        patch(
            "app.infrastructure.external_task_sync.TrelloClient.update_card_list",
            new=AsyncMock(),
        ) as update_card_list,
        patch("app.infrastructure.external_task_sync.record_event", new=AsyncMock()),
    ):
        synced = await sync_external_task_state(session, task)

    assert synced is True
    update_card_list.assert_awaited_once_with("card-1", "done")
    assert snapshot.state_id == "done"
