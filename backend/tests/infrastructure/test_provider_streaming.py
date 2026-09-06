from collections.abc import AsyncIterator

import pytest

from app.providers import AIProvider, ProviderModel, ProviderRequest, ProviderResponse
from app.providers.streaming import (
    ProviderStreamCancelled,
    ProviderStreamEvent,
    collect_provider_stream,
    iter_sse_json,
    normalize_stream_event,
)


class StreamingProvider(AIProvider):
    async def run(self, request: ProviderRequest) -> ProviderResponse:
        raise AssertionError("stream collector must not call the buffered path")

    async def list_models(self) -> list[ProviderModel]:
        return []

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(text_delta="hel", request_id="req-1", input_tokens=4)
        yield ProviderStreamEvent(text_delta="lo", output_tokens=2, completed=True)


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


@pytest.mark.asyncio
async def test_stream_collector_preserves_text_usage_and_progress() -> None:
    deltas: list[str] = []

    async def progress(delta: str) -> None:
        deltas.append(delta)

    response = await collect_provider_stream(
        StreamingProvider("secret"),
        ProviderRequest(model="test", system="system", prompt="prompt"),
        progress,
    )

    assert response == ProviderResponse("hello", "req-1", 4, 2)
    assert deltas == ["hel", "lo"]


@pytest.mark.asyncio
async def test_stream_collector_closes_stream_when_job_authority_is_revoked() -> None:
    checks = 0
    closed = False

    class LongStreamingProvider(StreamingProvider):
        async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
            nonlocal closed
            try:
                yield ProviderStreamEvent(text_delta="first")
                yield ProviderStreamEvent(text_delta="second")
            finally:
                closed = True

    async def is_cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(ProviderStreamCancelled, match="lease revocation"):
        await collect_provider_stream(
            LongStreamingProvider("secret"),
            ProviderRequest(model="test", system="system", prompt="prompt"),
            is_cancelled=is_cancelled,
        )

    assert closed is True
