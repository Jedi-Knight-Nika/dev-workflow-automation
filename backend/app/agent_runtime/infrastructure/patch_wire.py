"""Provider wire contracts for bounded artifacts; no provider tools or arbitrary URLs."""

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent_runtime.infrastructure.prompt_cache import bounded_request_context

KEYS = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
ENDPOINTS = {
    "openai": "https://api.openai.com/v1/responses",
    "deepseek": "https://api.deepseek.com/chat/completions",
}


def request_payload(
    provider: str,
    model: str,
    instructions: str,
    packet: dict[str, Any],
    schema: dict[str, Any],
    effort: str,
    output_limit: int,
) -> dict[str, Any]:
    if provider == "openai":
        return {
            **bounded_request_context(model, instructions, packet),
            "model": model,
            "store": False,
            "reasoning": {"effort": effort},
            "text": {"verbosity": "low", "format": schema},
            "max_output_tokens": output_limit,
        }
    if provider != "deepseek":
        raise ValueError("Unsupported bounded patch provider")
    # JSON mode does not enforce a schema. Each artifact is validated locally.
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": instructions
                + "\nReturn JSON matching this schema:\n"
                + json.dumps(schema["schema"]),
            },
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
        "thinking": {"type": "disabled" if effort == "none" else "enabled"},
        # DeepSeek has no medium tier: use low rather than exceed the approved ceiling.
        "reasoning_effort": "high" if effort == "high" else "low",
        "max_tokens": output_limit,
    }


def authorization(provider: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ[KEYS[provider]]}"}


def normalize_response(provider: str, data: dict[str, Any]) -> dict[str, Any]:
    if provider == "openai":
        return data
    if provider != "deepseek":
        raise ValueError("Unsupported bounded patch provider")
    raw = data.get("usage") or {}
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    return {
        "status": "completed" if choice.get("finish_reason") == "stop" else "incomplete",
        "usage": {
            "input_tokens": raw.get("prompt_tokens"),
            "output_tokens": raw.get("completion_tokens"),
            "input_tokens_details": {
                "cached_tokens": raw.get("prompt_cache_hit_tokens"),
                "cache_write_tokens": 0,
            },
            "output_tokens_details": {
                "reasoning_tokens": (raw.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens"
                )
            },
        },
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": (choice.get("message") or {}).get("content") or "",
                    }
                ],
            }
        ],
    }


class PatchEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=1000)
    old_text: str
    new_text: str


class PatchArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    outcome: Literal["PATCH", "BLOCKED"]
    summary: str = Field(max_length=10000)
    edits: list[PatchEdit] = Field(max_length=100)


def validate_artifact(provider: str, schema: dict[str, Any], value: Any) -> None:
    if provider == "deepseek" and schema.get("name") == "complete_patch":
        PatchArtifact.model_validate(value)
    # Plans and investigations are validated by their domain-specific Pydantic callers.
