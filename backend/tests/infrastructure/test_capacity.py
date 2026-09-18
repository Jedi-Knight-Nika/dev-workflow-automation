from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.agent_runtime.infrastructure import capacity
from app.platform.configuration.settings import Settings


@pytest.mark.parametrize("memory,cpus,warning", [(32 * 1024**3, 16, False), (4 * 1024**3, 2, True)])
async def test_capacity_uses_docker_limits_without_changing_settings(
    monkeypatch, memory, cpus, warning
):
    client = AsyncMock()
    client.get.return_value = httpx.Response(
        200,
        json={"MemTotal": memory, "NCPU": cpus},
        request=httpx.Request("GET", "http://docker/info"),
    )
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    monkeypatch.setattr(capacity.httpx, "AsyncClient", Mock(return_value=manager))
    log = Mock()
    monkeypatch.setattr(capacity.structlog, "get_logger", Mock(return_value=log))
    settings = Settings(_env_file=None, global_developer_slots=2, validation_slots=2)
    await capacity.check_host_capacity(settings)
    assert log.warning.called == warning
    assert settings.global_developer_slots == settings.validation_slots == 2
