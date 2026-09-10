import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.engineering.infrastructure import validation


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_validation_drains_buffered_output_before_waiting_after_stop(
    tmp_path, monkeypatch, cancelled
):
    failure = asyncio.CancelledError() if cancelled else TimeoutError()
    chunks = iter([failure, b"x" * 8192, b"last error", b""])
    drained = False

    async def read(size):
        nonlocal drained
        item = next(chunks)
        if isinstance(item, BaseException):
            raise item
        if not item:
            drained = True
        return item

    async def wait():
        assert drained, "Waiting on an undrained pipe can hang after process exit"

    process = SimpleNamespace(
        pid=123,
        returncode=-signal.SIGKILL,
        stdout=SimpleNamespace(read=read),
        wait=AsyncMock(side_effect=wait),
    )
    kill = Mock()
    monkeypatch.setattr(validation.os, "killpg", kill)
    monkeypatch.setattr(
        validation.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await validation.run_check(("check",), workspace=tmp_path, output_limit=100)
    else:
        result = await validation.run_check(("check",), workspace=tmp_path, output_limit=100)
        assert result.timed_out and not result.passed
        assert len(result.output_tail) == 100
        assert result.output_tail.endswith("last error")
    kill.assert_called_once_with(123, signal.SIGKILL)
    process.wait.assert_awaited_once()
