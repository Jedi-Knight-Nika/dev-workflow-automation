from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.delivery.infrastructure.status_sync import (
    ExternalStatusSync,
    enqueue_status,
    process_status_sync,
)
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure.linear_client import LinearClient
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.intake.infrastructure.trello_client import TrelloClient
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from tests.integration.test_v2_enrollment_and_costs import scenario

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("provider", ["trello", "linear"])
async def test_merged_status_is_durable_idempotent_and_requires_explicit_target(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        integration_id = None
        method = AsyncMock()
        monkeypatch.setattr(TrelloClient, "update_card_list", method)
        monkeypatch.setattr(LinearClient, "update_issue_state", method)
        try:
            async with postgres_session_factory.begin() as session:
                integration = await session.scalar(
                    select(Integration).where(Integration.provider_name == provider)
                )
                assert integration and integration.encrypted_credentials is None
                assert integration.configuration == {}
                integration_id = integration.id
                integration.encrypted_credentials = cipher.encrypt(
                    '{"api_key":"test-only","token":"test-only"}'
                    if provider == "trello"
                    else "test-only"
                )
                session.add(
                    ExternalTaskSnapshot(
                        task_id=task_id,
                        provider=provider,
                        external_id="fixture-ticket",
                        identifier="FIXTURE-1",
                        state_id="in-progress",
                        raw_payload={},
                    )
                )
                task = await session.get(Task, task_id, with_for_update=True)
                assert task
                task.status, task.stage = "MERGED", "COMPLETE"
                await enqueue_status(session, task.id, 7, "MERGED", "COMPLETE")
            assert await process_status_sync(postgres_session_factory)
            method.assert_not_called()
            async with postgres_session_factory.begin() as session:
                outbox = await session.get(ExternalStatusSync, task_id)
                assert outbox and outbox.status == "CONFIGURATION_REQUIRED"
                integration = await session.get(Integration, integration_id)
                assert integration
                suffix = "list_id" if provider == "trello" else "state_id"
                integration.configuration = {f"done_{suffix}": "done-exact-id"}
                await enqueue_status(session, task_id, 7, "MERGED", "COMPLETE")
            assert await process_status_sync(postgres_session_factory)
            method.assert_awaited_once_with("fixture-ticket", "done-exact-id")
            assert not await process_status_sync(postgres_session_factory)
            async with postgres_session_factory() as session:
                snapshot = await session.scalar(
                    select(ExternalTaskSnapshot).where(ExternalTaskSnapshot.task_id == task_id)
                )
                assert snapshot and snapshot.state_id == "done-exact-id"
        finally:
            async with postgres_session_factory.begin() as session:
                await session.execute(
                    update(Integration)
                    .where(Integration.id == integration_id)
                    .values(encrypted_credentials=None, configuration={})
                )
