import pytest

from app.domain.ai_runtime import ReasoningLevel, resolve_runtime_config
from app.providers.capabilities import ModelCapabilityRegistry


def test_agent_inherits_role_runtime_and_strategy_stays_inside_ceiling() -> None:
    capabilities = ModelCapabilityRegistry().get("openai", "gpt-5.4")
    runtime = resolve_runtime_config(
        provider="openai",
        model="gpt-5.4",
        role_profile={
            "reasoning_default": "MEDIUM",
            "reasoning_min": "LOW",
            "reasoning_max": "HIGH",
            "max_tool_calls": 40,
        },
        agent_overrides={},
        override_policy={},
        strategy={"kind": "HIGH_ASSURANCE", "max_tool_calls": 80, "max_job_turns": 24},
        capabilities=capabilities,
    )

    assert runtime.reasoning_level == ReasoningLevel.HIGH
    assert runtime.max_tool_calls == 40
    assert runtime.max_model_turns == 3


def test_sparse_agent_override_changes_only_allowed_value() -> None:
    capabilities = ModelCapabilityRegistry().get("openai", "gpt-5.4")
    runtime = resolve_runtime_config(
        provider="openai",
        model="gpt-5.4",
        role_profile={"reasoning_default": "HIGH", "context_strategy": "DEEP"},
        agent_overrides={"reasoning_level": "LOW"},
        override_policy={"reasoning_level": "ALLOW_WITHIN_RANGE"},
        strategy=None,
        capabilities=capabilities,
    )

    assert runtime.reasoning_level == ReasoningLevel.LOW
    assert runtime.context_strategy == "DEEP"


def test_locked_agent_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not allow overriding max_tool_calls"):
        resolve_runtime_config(
            provider="openai",
            model="gpt-5.4",
            role_profile={},
            agent_overrides={"max_tool_calls": 100},
            override_policy={"max_tool_calls": "LOCKED"},
            strategy=None,
            capabilities=ModelCapabilityRegistry().get("openai", "gpt-5.4"),
        )


def test_agent_cannot_expand_role_tool_budget() -> None:
    with pytest.raises(ValueError, match="exceeds the Role limit"):
        resolve_runtime_config(
            provider="openai",
            model="gpt-5.4",
            role_profile={"max_tool_calls": 40},
            agent_overrides={"max_tool_calls": 41},
            override_policy={"max_tool_calls": "ALLOW_WITHIN_RANGE"},
            strategy=None,
            capabilities=ModelCapabilityRegistry().get("openai", "gpt-5.4"),
        )


def test_unsupported_temperature_is_rejected_before_provider_call() -> None:
    with pytest.raises(ValueError, match="temperature override"):
        resolve_runtime_config(
            provider="google",
            model="gemini-3.5-flash",
            role_profile={"temperature": 0.2},
            agent_overrides={},
            override_policy={},
            strategy=None,
            capabilities=ModelCapabilityRegistry().get("google", "gemini-3.5-flash"),
        )


def test_effective_snapshot_is_stable_and_contains_no_credentials() -> None:
    runtime = resolve_runtime_config(
        provider="anthropic",
        model="claude-opus-4-8",
        role_profile={"reasoning_default": "HIGH"},
        agent_overrides={},
        override_policy={},
        strategy=None,
        capabilities=ModelCapabilityRegistry().get("anthropic", "claude-opus-4-8"),
    )

    assert runtime.fingerprint() == runtime.fingerprint()
    assert "api_key" not in runtime.snapshot()
