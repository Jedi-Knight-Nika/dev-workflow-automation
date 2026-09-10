from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.usage import Pricing


@pytest.fixture(autouse=True)
def injected_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "acceptance-fake-key")
    monkeypatch.setenv("HOME", str(tmp_path))


def test_batched_distinct_reads_do_not_trigger_repeated_read_stop(tmp_path):
    sdk = pytest.importorskip("openai_codex")
    from openai_codex.generated.v2_all import CommandAction

    from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
    from app.agent_runtime.infrastructure.codex import CodexHarness

    actions = [
        CommandAction.model_validate(
            {"type": "read", "path": path, "name": path, "command": "sed -n '1,120p' " + path}
        )
        for path in ["layout.svelte", "draggable.ts", "workflow.spec.ts"]
    ]
    with patch.object(sdk, "AsyncCodex", return_value=AsyncMock()):
        harness = CodexHarness(
            HarnessSettings(
                "model", tmp_path, "contract", token_policy=TokenEfficiencyPolicy(mode="ENFORCE")
            )
        )
        harness._record_reads(actions, "batch", 45000)
        assert harness.governor.source_read_count == 3
        assert harness.governor.source_read_bytes == 45000
        assert harness.governor.repeated_read_count == 0
        assert harness.governor.observe(62000, 18000)[1] is None
        harness._record_reads(actions, "batch", 45000)
        harness._record_reads(actions, "batch", 45000)
        assert harness.governor.observe(63000, 18000)[1] == "REPEATED_READ_LOOP"


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


def test_supervisor_checkpoint_precedes_exploration_stop(tmp_path):
    sdk = pytest.importorskip("openai_codex")
    from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
    from app.agent_runtime.infrastructure.codex import CodexHarness

    with patch.object(sdk, "AsyncCodex", return_value=AsyncMock()):
        harness = CodexHarness(
            HarnessSettings(
                "model", tmp_path, "contract", token_policy=TokenEfficiencyPolicy(mode="ENFORCE")
            )
        )
        for total in (13000, 28000, 46000):
            harness.governor.observe(total, 18000)
        assert harness._early_checkpoint_due()
        assert harness.governor.stop_reason is None
        harness.supervised_kinds.add("NO_PROGRESS")
        assert not harness._early_checkpoint_due()


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


@pytest.mark.asyncio
async def test_codex_live_cache_uses_deltas_not_sum_of_cumulative_receipts(tmp_path):
    sdk = pytest.importorskip("openai_codex")
    from openai_codex.generated.v2_all import (
        ThreadTokenUsageUpdatedNotification,
        TurnCompletedNotification,
    )

    from app.agent_runtime.infrastructure.codex import CodexHarness

    async def stream():
        for total_input, cached in [(1000, 200), (2200, 1100), (3500, 2300)]:
            total = {
                "inputTokens": total_input,
                "outputTokens": 10,
                "cachedInputTokens": cached,
                "reasoningOutputTokens": 0,
                "totalTokens": total_input + 10,
            }
            yield SimpleNamespace(
                payload=ThreadTokenUsageUpdatedNotification.model_validate(
                    {
                        "threadId": "thread",
                        "turnId": "turn",
                        "tokenUsage": {"last": total, "total": total},
                    }
                )
            )
        yield SimpleNamespace(
            payload=TurnCompletedNotification.model_validate(
                {"threadId": "thread", "turn": {"id": "turn", "items": [], "status": "completed"}}
            )
        )

    with patch.object(sdk, "AsyncCodex", return_value=AsyncMock()):
        harness = CodexHarness(
            HarnessSettings(
                "model", tmp_path, "contract", pricing=Pricing(Decimal(1), Decimal(1), Decimal(0))
            )
        )
        harness.thread = SimpleNamespace(id="thread")
        harness.previous_usage = dict.fromkeys(
            [
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "cache_write_input_tokens",
                "reasoning_output_tokens",
            ],
            0,
        )
        harness.turn = SimpleNamespace(stream=stream, interrupt=AsyncMock())
        receipt = await harness._collect()
    assert receipt.token_efficiency["cached_input_tokens_observed"] == 2300
    assert receipt.token_efficiency["inference_cycle_count"] == 3
    assert receipt.usage.cache_read_input_tokens == 2300


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["CONTINUE", "NUDGE", "STOP"])
async def test_live_supervisor_is_bounded_deduplicated_and_never_starts_a_new_turn(
    tmp_path, action
):
    sdk = pytest.importorskip("openai_codex")
    from app.agent_runtime.infrastructure.codex import CodexHarness

    callback = AsyncMock(
        return_value={"action": action, "message": "Use installed formatter from frontend"}
    )
    client = AsyncMock()
    with patch.object(sdk, "AsyncCodex", return_value=client):
        harness = CodexHarness(
            HarnessSettings("model", tmp_path, "contract", supervision_callback=callback)
        )
        harness.turn = SimpleNamespace(steer=AsyncMock(), interrupt=AsyncMock())
        await harness._supervise_anomaly("TOOL_FAILURE", "error" * 1000)
        await harness._supervise_anomaly("TOOL_FAILURE", "same error")
        await harness._supervise_anomaly("NO_PROGRESS", "same state")
        await harness._supervise_anomaly("THIRD", "cannot spend again")
    assert callback.await_count == (1 if action == "STOP" else 2)
    assert len(callback.call_args_list[0].args[0]["detail"]) <= 1600
    assert harness.turn.steer.await_count == (2 if action == "NUDGE" else 0)
    assert harness.turn.interrupt.await_count == (1 if action == "STOP" else 0)
    assert not client.mock_calls
