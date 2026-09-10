from typing import Any

from app.agent_runtime.domain.usage import Usage


def request_body(
    provider: str, model: str, messages: list[dict[str, str]]
) -> tuple[str, dict[str, Any]]:
    if provider == "openai":
        return "https://api.openai.com/v1/responses", {
            "model": model,
            "input": messages,
            "max_output_tokens": 512,
            "store": False,
            "text": {"format": {"type": "json_object"}},
        }
    if provider == "deepseek":
        return "https://api.deepseek.com/chat/completions", {
            "model": model,
            "messages": messages,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
    raise ValueError("Unsupported bounded cloud interpreter provider")


def normalized_usage(provider: str, raw: dict[str, Any]) -> Usage:
    if provider == "deepseek":
        return Usage(
            raw.get("prompt_tokens"),
            raw.get("completion_tokens"),
            raw.get("prompt_cache_hit_tokens"),
            0,
            (raw.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        )
    return Usage(
        raw.get("input_tokens"),
        raw.get("output_tokens"),
        (raw.get("input_tokens_details") or {}).get("cached_tokens"),
        (raw.get("input_tokens_details") or {}).get("cache_write_tokens", 0),
        (raw.get("output_tokens_details") or {}).get("reasoning_tokens"),
    )


def response_text(provider: str, data: dict[str, Any]) -> str:
    if provider == "deepseek":
        return str(data["choices"][0]["message"].get("content") or "")
    return "".join(
        part["text"]
        for item in data.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
