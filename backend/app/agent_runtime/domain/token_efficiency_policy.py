"""Versioned policy for one Developer, independent of invoice admission."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TokenEfficiencyPolicy:
    execution_profile: str = "STANDARD"
    mode: str = "INSTRUMENT"
    reasoning_effort: str = "medium"
    first_edit_warning_tokens: int = 40000
    exploration_hard_tokens: int = 70000
    no_progress_tokens: int = 35000
    active_context_soft_tokens: int = 120000
    active_context_hard_tokens: int = 170000
    repeated_command_threshold: int = 3
    repeated_failure_threshold: int = 3
    max_rollovers: int = 3
    max_compactions: int = 2
    max_model_visible_tool_result_tokens: int = 4000
    automatic_rollover: bool = False

    def __post_init__(self) -> None:
        if self.execution_profile not in {"FAST", "STANDARD", "LARGE", "CUSTOM"}:
            raise ValueError("Unknown execution profile")
        if self.mode not in {"INSTRUMENT", "WARN", "ENFORCE"}:
            raise ValueError("Unknown governor mode")
        if self.reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("Unknown reasoning effort")
        for key, value in asdict(self).items():
            if key.endswith("tokens") and (type(value) is not int or not 1000 <= value <= 1000000):
                raise ValueError("Token limits must be integers between 1,000 and 1,000,000")
        if not self.first_edit_warning_tokens < self.exploration_hard_tokens:
            raise ValueError("Exploration stop must follow its warning")
        if not self.active_context_soft_tokens < self.active_context_hard_tokens <= 250000:
            raise ValueError("Context ceilings must be ordered and at most 250,000")
        if self.max_model_visible_tool_result_tokens > 10000:
            raise ValueError("A tool context item cannot exceed 10,000 tokens")
        for value in (self.repeated_command_threshold, self.repeated_failure_threshold):
            if type(value) is not int or not 2 <= value <= 20:
                raise ValueError("Loop thresholds must be integers between 2 and 20")
        if not 0 <= self.max_rollovers <= 10 or not 0 <= self.max_compactions <= 5:
            raise ValueError("Context transitions must be bounded")
        if type(self.automatic_rollover) is not bool:
            raise ValueError("Automatic rollover must be boolean")

    @classmethod
    def parse(cls, values: dict[str, Any] | None = None) -> "TokenEfficiencyPolicy":
        values = values or {}
        profile = values.get("execution_profile", "STANDARD")
        defaults: dict[str, Any] = {}
        if profile == "FAST":
            defaults = {
                "reasoning_effort": "low",
                "first_edit_warning_tokens": 20000,
                "exploration_hard_tokens": 35000,
                "no_progress_tokens": 20000,
                "active_context_soft_tokens": 70000,
                "active_context_hard_tokens": 100000,
                "repeated_failure_threshold": 2,
                "max_rollovers": 1,
            }
        elif profile == "LARGE":
            defaults = {
                "first_edit_warning_tokens": 60000,
                "exploration_hard_tokens": 110000,
                "no_progress_tokens": 50000,
                "active_context_soft_tokens": 160000,
                "active_context_hard_tokens": 220000,
                "repeated_command_threshold": 4,
                "max_rollovers": 6,
            }
        return cls(**(defaults | values))
