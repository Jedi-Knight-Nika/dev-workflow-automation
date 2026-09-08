from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.usage import Pricing


@pytest.fixture(autouse=True)
def injected_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "acceptance-fake-key")


@pytest.mark.asyncio
@pytest.mark.parametrize("budget,interrupts", [(Decimal(1), 0), (Decimal("0.0001"), 1)])
async def test_codex_stream_guard_uses_sdk_defaults_and_interrupts_at_budget(
    tmp_path: Path, budget: Decimal, interrupts: int
) -> None:
    sdk = pytest.importorskip("openai_codex")
    from openai_codex.generated.v2_all import (
        ThreadTokenUsageUpdatedNotification,
        TurnCompletedNotification,
    )

    from app.agent_runtime.infrastructure.codex import CodexHarness

    totals = {
        "inputTokens": 1000,
        "outputTokens": 100,
        "cachedInputTokens": 0,
        "reasoningOutputTokens": 10,
        "totalTokens": 1100,
    }
    usage = ThreadTokenUsageUpdatedNotification.model_validate(
        {"threadId": "thread", "turnId": "turn", "tokenUsage": {"last": totals, "total": totals}}
    )
    completed = TurnCompletedNotification.model_validate(
        {"threadId": "thread", "turn": {"id": "turn", "items": [], "status": "completed"}}
    )

    async def stream():
        yield SimpleNamespace(payload=usage)
        yield SimpleNamespace(payload=completed)

    turn = SimpleNamespace(stream=stream, interrupt=AsyncMock())
    client = AsyncMock()
    client.thread_start.return_value.id = "thread"
    client.thread_start.return_value.turn.return_value = turn
    with patch.object(sdk, "AsyncCodex", return_value=client):
        harness = CodexHarness(
            HarnessSettings(
                "gpt-5.6-terra",
                tmp_path,
                "contract",
                max_cost_usd=budget,
                pricing=Pricing(Decimal(1), Decimal(1), Decimal(0)),
            )
        )
        await harness.start()
        receipt = await harness.run_turn("Implement the task")
    assert turn.interrupt.await_count == interrupts
    assert receipt.usage.complete
    assert receipt.usage.cache_write_input_tokens == 0
    assert receipt.status == ("interrupted" if interrupts else "completed")


@pytest.mark.asyncio
async def test_codex_compaction_uses_native_api_and_metered_turn(tmp_path: Path) -> None:
    sdk = pytest.importorskip("openai_codex")
    from openai_codex.generated.v2_all import TurnStartedNotification

    from app.agent_runtime.infrastructure.codex import CodexHarness

    notification = TurnStartedNotification.model_validate(
        {"threadId": "thread", "turn": {"id": "compact-turn", "items": [], "status": "inProgress"}}
    )
    client = AsyncMock()
    client.thread_start.return_value.id = "thread"
    client._client.next_notification.return_value = SimpleNamespace(payload=notification)
    with patch.object(sdk, "AsyncCodex", return_value=client):
        harness = CodexHarness(HarnessSettings("model", tmp_path, "contract"))
        await harness.start()
        with patch.object(harness, "_collect", new_callable=AsyncMock) as collect:
            await harness.compact()
            collect.assert_awaited_once()
    client.thread_start.return_value.compact.assert_awaited_once()
    assert harness.turn.id == "compact-turn"
