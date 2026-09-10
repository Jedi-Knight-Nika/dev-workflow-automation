import asyncio
from unittest.mock import AsyncMock

import pytest

from app.supervisor.application.supervise import run_supervisor


@pytest.mark.asyncio
async def test_saved_decision_never_calls_provider():
    port = AsyncMock()
    port.admit.return_value = "saved"
    assert await run_supervisor(port) == "saved"
    port.decide.assert_not_called()
    port.complete.assert_not_called()


@pytest.mark.asyncio
async def test_admission_precedes_provider_and_completion():
    events = []

    class Port:
        async def admit(self):
            events.append("admit")

        async def decide(self):
            events.append("decide")
            return "decision"

        async def complete(self, decision):
            assert decision == "decision"
            events.append("complete")

        async def fail(self, error):
            pytest.fail("Successful decision must not record failure")

    assert await run_supervisor(Port()) == "decision"
    assert events == ["admit", "decide", "complete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["admit", "decide", "complete"])
@pytest.mark.parametrize("error", [ValueError("failure"), asyncio.CancelledError()])
async def test_errors_preserve_receipt_without_retry(stage, error):
    port = AsyncMock()
    port.admit.return_value = None
    getattr(port, stage).side_effect = error
    with pytest.raises(type(error)):
        await run_supervisor(port)
    if stage == "admit":
        port.fail.assert_not_called()
        port.decide.assert_not_called()
    else:
        port.fail.assert_awaited_once_with(error)
        port.decide.assert_awaited_once()
