import asyncio
from unittest.mock import Mock

import pytest

from app.bootstrap import messaging
from app.platform.configuration.settings import Settings


async def test_default_mode_does_not_open_storage_or_construct_workers(monkeypatch):
    sessions = Mock(side_effect=AssertionError("Default mode opened storage"))
    projector = Mock(side_effect=AssertionError("Default mode constructed a worker"))
    monkeypatch.setattr(messaging, "activity_sessions", sessions)
    monkeypatch.setattr(messaging, "create_activity_projector", projector)
    running = asyncio.create_task(
        messaging.run_messaging(Settings(_env_file=None, event_transport="postgres"))
    )
    await asyncio.sleep(0)
    assert not running.done()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    sessions.assert_not_called()
    projector.assert_not_called()


async def test_rabbit_mode_requires_explicit_connection_configuration():
    with pytest.raises(ValueError, match="RABBITMQ_URL"):
        await messaging.run_messaging(
            Settings(_env_file=None, event_transport="rabbitmq", rabbitmq_url="")
        )
