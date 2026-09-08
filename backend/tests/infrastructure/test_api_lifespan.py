import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import Settings


@pytest.mark.asyncio
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_lifespan_releases_background_tasks_even_when_scheduler_start_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, startup_failure: bool
) -> None:
    from app import main

    scheduler = AsyncMock()
    if startup_failure:
        scheduler.start.side_effect = RuntimeError("Recovery unavailable")
    factory = Mock(return_value=scheduler)
    close_pool = AsyncMock()
    monkeypatch.setattr(main, "settings", Settings(workspace_root=tmp_path, scheduler_enabled=True))
    monkeypatch.setattr(main, "create_scheduler", factory)
    monkeypatch.setattr(main.integration_http_pool, "aclose", close_pool)
    monkeypatch.setattr(main, "notification_delivery_loop", AsyncMock(side_effect=lambda: None))
    previous_tasks = asyncio.all_tasks()
    if startup_failure:
        with pytest.raises(RuntimeError, match="Recovery unavailable"):
            async with main.lifespan(main.app):
                pytest.fail("Failed startup must not serve requests")
    else:
        async with main.lifespan(main.app):
            scheduler.start.assert_awaited_once()
    scheduler.stop.assert_awaited_once()
    close_pool.assert_awaited_once()
    assert asyncio.all_tasks() == previous_tasks
