from unittest.mock import AsyncMock

from claude_agent_sdk import AssistantMessage, ResultMessage

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.infrastructure.claude import ClaudeHarness


async def test_native_request_observations_deduplicate_message_chunks_and_reset_each_turn(tmp_path):
    harness = ClaudeHarness(HarnessSettings(model="test", workspace=tmp_path, instructions="test"))
    harness.governor.diff_fingerprint = "known"
    messages = [
        AssistantMessage(content=[], model="test", message_id=id)
        for id in ("first", "first", "second", None)
    ]
    messages.append(
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="session",
            result="IMPLEMENTED",
            usage={
                "input_tokens": 20,
                "output_tokens": 10,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        )
    )

    async def receive():
        for message in messages:
            yield message

    client = AsyncMock()
    client.receive_response = receive
    harness.client = client
    for _ in range(2):
        receipt = await harness.run_turn("test")
        assert receipt.raw_usage["request_count"] == 2
        assert receipt.raw_usage["request_count_complete"] is False
        assert receipt.usage.input_tokens == 20
        assert receipt.status == "completed"
    assert client.query.await_count == 2
