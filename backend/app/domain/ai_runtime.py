import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ReasoningLevel(StrEnum):
    PROVIDER_DEFAULT = "PROVIDER_DEFAULT"
    MINIMAL = "MINIMAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    MAX = "MAX"


REASONING_ORDER = tuple(ReasoningLevel)


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    provider: str
    model: str
    reasoning_levels: tuple[ReasoningLevel, ...] = (ReasoningLevel.PROVIDER_DEFAULT,)
    max_output_tokens: int | None = None
    temperature_supported: bool = False
    structured_output_supported: bool = False
    tools_supported: bool = False
    parallel_tool_calls_supported: bool = False
    version: str = "2026-09-06"


@dataclass(frozen=True, slots=True)
class EffectiveAgentRuntimeConfig:
    provider: str
    model: str
    reasoning_level: ReasoningLevel
    max_output_tokens: int
    temperature: float | None
    context_strategy: str
    max_tool_calls: int
    job_timeout_seconds: int
    max_job_attempts: int
    max_model_turns: int
    structured_output_mode: str
    capability_version: str
    strategy_version: str

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        encoded = json.dumps(self.snapshot(), sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


DEFAULT_RUNTIME_PROFILE: dict[str, Any] = {
    "reasoning_default": "PROVIDER_DEFAULT",
    "reasoning_min": "PROVIDER_DEFAULT",
    "reasoning_max": "MAX",
    "dynamic_reasoning_allowed": True,
    "max_output_tokens": None,
    "temperature": None,
    "context_strategy": "BALANCED",
    "max_tool_calls": 40,
    "job_timeout_seconds": 1800,
    "max_job_attempts": 2,
    "max_model_turns": 3,
    "structured_output_mode": "REQUIRED",
}

DEFAULT_OVERRIDE_POLICY: dict[str, str] = {
    "provider": "ALLOW",
    "model": "ALLOW",
    "reasoning_level": "ALLOW_WITHIN_RANGE",
    "max_output_tokens": "ALLOW",
    "temperature": "ALLOW_IF_SUPPORTED",
    "context_strategy": "ALLOW",
    "max_tool_calls": "ALLOW_WITHIN_RANGE",
    "job_timeout_seconds": "ALLOW_WITHIN_RANGE",
    "permissions": "REDUCE_ONLY",
    "system_instructions": "ADDITIVE_ONLY",
    "allowed_results": "LOCKED",
}


def _reasoning(value: object) -> ReasoningLevel:
    normalized = str(value or "PROVIDER_DEFAULT").upper()
    if normalized == "DEFAULT":
        normalized = "PROVIDER_DEFAULT"
    return ReasoningLevel(normalized)


def _clamp_reasoning(
    requested: ReasoningLevel, minimum: ReasoningLevel, maximum: ReasoningLevel
) -> ReasoningLevel:
    position = REASONING_ORDER.index(requested)
    return REASONING_ORDER[
        min(max(position, REASONING_ORDER.index(minimum)), REASONING_ORDER.index(maximum))
    ]


def resolve_runtime_config(
    *,
    provider: str,
    model: str,
    role_profile: dict[str, Any] | None,
    agent_overrides: dict[str, Any] | None,
    override_policy: dict[str, str] | None,
    strategy: dict[str, Any] | None,
    capabilities: ModelCapabilities,
) -> EffectiveAgentRuntimeConfig:
    profile = {**DEFAULT_RUNTIME_PROFILE, **(role_profile or {})}
    policy = {**DEFAULT_OVERRIDE_POLICY, **(override_policy or {})}
    for key, value in (agent_overrides or {}).items():
        mode = policy.get(key, "LOCKED")
        if mode == "LOCKED":
            raise ValueError(f"Role does not allow overriding {key}")
        profile_key = "reasoning_default" if key == "reasoning_level" else key
        if (
            mode == "ALLOW_WITHIN_RANGE"
            and key
            in {
                "max_tool_calls",
                "job_timeout_seconds",
            }
            and int(value) > int(profile[profile_key])
        ):
            raise ValueError(f"Agent override exceeds the Role limit for {key}")
        profile[profile_key] = value
    minimum = _reasoning(profile["reasoning_min"])
    maximum = _reasoning(profile["reasoning_max"])
    if REASONING_ORDER.index(minimum) > REASONING_ORDER.index(maximum):
        raise ValueError("Reasoning minimum cannot exceed maximum")
    requested = _reasoning(profile["reasoning_default"])
    if profile["dynamic_reasoning_allowed"] and strategy:
        kind = str(strategy.get("kind", "STANDARD"))
        requested = {
            "FAST": ReasoningLevel.LOW,
            "HIGH_ASSURANCE": ReasoningLevel.HIGH,
            "PARALLEL_INVESTIGATION": ReasoningLevel.HIGH,
        }.get(kind, requested)
    reasoning = _clamp_reasoning(requested, minimum, maximum)
    if reasoning not in capabilities.reasoning_levels:
        supported = [
            item
            for item in capabilities.reasoning_levels
            if item != ReasoningLevel.PROVIDER_DEFAULT
            and REASONING_ORDER.index(item) <= REASONING_ORDER.index(reasoning)
        ]
        reasoning = supported[-1] if supported else ReasoningLevel.PROVIDER_DEFAULT
    output_limit = int(profile["max_output_tokens"] or capabilities.max_output_tokens or 4096)
    if output_limit < 256:
        raise ValueError("Maximum output must be at least 256 tokens")
    if capabilities.max_output_tokens:
        output_limit = min(output_limit, capabilities.max_output_tokens)
    temperature = profile.get("temperature")
    if temperature is not None:
        if not capabilities.temperature_supported:
            raise ValueError(f"{provider}/{model} does not support a temperature override")
        temperature = float(temperature)
        if not 0 <= temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2")
    strategy_tool_limit = int((strategy or {}).get("max_tool_calls", profile["max_tool_calls"]))
    strategy_turn_limit = int((strategy or {}).get("max_job_turns", profile["max_model_turns"]))
    if str(profile["context_strategy"]) not in {"MINIMAL", "BALANCED", "DEEP"}:
        raise ValueError("Context strategy must be MINIMAL, BALANCED, or DEEP")
    if not 1 <= int(profile["max_tool_calls"]) <= 200:
        raise ValueError("Maximum tool calls must be between 1 and 200")
    if not 60 <= int(profile["job_timeout_seconds"]) <= 43_200:
        raise ValueError("Job timeout must be between 60 and 43200 seconds")
    return EffectiveAgentRuntimeConfig(
        provider=provider,
        model=model,
        reasoning_level=reasoning,
        max_output_tokens=output_limit,
        temperature=temperature,
        context_strategy=str(profile["context_strategy"]),
        max_tool_calls=min(int(profile["max_tool_calls"]), strategy_tool_limit, 200),
        job_timeout_seconds=min(int(profile["job_timeout_seconds"]), 43_200),
        max_job_attempts=min(int(profile["max_job_attempts"]), 10),
        max_model_turns=min(int(profile["max_model_turns"]), strategy_turn_limit, 20),
        structured_output_mode=str(profile["structured_output_mode"]),
        capability_version=capabilities.version,
        strategy_version=str((strategy or {}).get("version", "v1")),
    )
