from collections.abc import AsyncIterator

import pytest

from app.providers.streaming import iter_sse_json, normalize_stream_event


async def lines(*values: str) -> AsyncIterator[str]:
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_sse_decoder_handles_labels_multiline_data_and_done() -> None:
    events = [
        event
        async for event in iter_sse_json(
            lines(
                ": keepalive",
                "event: delta",
                'data: {"type":',
                'data: "example"}',
                "",
                "data: [DONE]",
                "",
            )
        )
    ]

    assert events == [{"type": "example"}]


def test_provider_text_deltas_are_normalized_without_thought_content() -> None:
    openai = normalize_stream_event(
        "openai", {"type": "response.output_text.delta", "delta": "hello"}
    )
    anthropic = normalize_stream_event(
        "anthropic",
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}},
    )
    google = normalize_stream_event(
        "google", {"event_type": "step.delta", "delta": {"type": "text", "text": "hey"}}
    )
    thought = normalize_stream_event(
        "google",
        {"event_type": "step.delta", "delta": {"type": "thought_summary", "text": "hidden"}},
    )

    assert [openai.text_delta, anthropic.text_delta, google.text_delta] == ["hello", "hi", "hey"]
    assert thought is None


def test_completion_usage_is_normalized() -> None:
    event = normalize_stream_event(
        "openai",
        {
            "type": "response.completed",
            "response": {
                "id": "resp_1",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        },
    )

    assert event is not None
    assert event.completed is True
    assert (event.request_id, event.input_tokens, event.output_tokens) == ("resp_1", 10, 4)
