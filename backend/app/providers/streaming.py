import json
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.providers.base import AIProvider, ProviderRequest, ProviderResponse


@dataclass(frozen=True, slots=True)
class ProviderStreamEvent:
    text_delta: str = ""
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    completed: bool = False


async def collect_provider_stream(
    provider: AIProvider,
    request: ProviderRequest,
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
) -> ProviderResponse:
    """Collect streamed answer text into the existing auditable response contract."""
    text_parts: list[str] = []
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    async for event in provider.stream(request):
        if event.text_delta:
            text_parts.append(event.text_delta)
            if on_text_delta is not None:
                await on_text_delta(event.text_delta)
        request_id = event.request_id or request_id
        input_tokens = event.input_tokens if event.input_tokens is not None else input_tokens
        output_tokens = event.output_tokens if event.output_tokens is not None else output_tokens
    return ProviderResponse(
        text="".join(text_parts),
        request_id=request_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def iter_sse_json(lines: AsyncIterable[str]) -> AsyncIterator[dict[str, Any]]:
    """Decode JSON SSE data frames while ignoring comments and provider event labels."""
    data_lines: list[str] = []
    async for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines.clear()
                if payload != "[DONE]":
                    value = json.loads(payload)
                    if isinstance(value, dict):
                        yield value
            continue
        if line.startswith((":", "event:", "id:")):
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())
    if data_lines:
        payload = "\n".join(data_lines)
        if payload != "[DONE]":
            value = json.loads(payload)
            if isinstance(value, dict):
                yield value


def normalize_stream_event(provider: str, event: dict[str, Any]) -> ProviderStreamEvent | None:
    """Map public provider SSE envelopes without exposing reasoning/thought deltas."""
    if provider == "openai":
        if event.get("type") == "response.output_text.delta":
            return ProviderStreamEvent(text_delta=str(event.get("delta") or ""))
        if event.get("type") == "response.completed":
            response = event.get("response") or {}
            usage = response.get("usage") or {}
            return ProviderStreamEvent(
                request_id=response.get("id"),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                completed=True,
            )
    elif provider == "anthropic":
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                return ProviderStreamEvent(text_delta=str(delta.get("text") or ""))
        if event.get("type") == "message_start":
            message = event.get("message") or {}
            usage = message.get("usage") or {}
            return ProviderStreamEvent(
                request_id=message.get("id"), input_tokens=usage.get("input_tokens")
            )
        if event.get("type") == "message_delta":
            usage = event.get("usage") or {}
            return ProviderStreamEvent(output_tokens=usage.get("output_tokens"), completed=True)
    elif provider == "google":
        event_type = event.get("event_type")
        delta = event.get("delta") or {}
        if event_type == "step.delta" and delta.get("type") == "text":
            return ProviderStreamEvent(text_delta=str(delta.get("text") or ""))
        if event_type == "interaction.completed":
            interaction = event.get("interaction") or {}
            usage = interaction.get("usage") or {}
            return ProviderStreamEvent(
                request_id=interaction.get("id"),
                input_tokens=usage.get("total_input_tokens"),
                output_tokens=usage.get("total_output_tokens"),
                completed=True,
            )
    return None
