"""Explicit per-role routing. No model may choose a provider, model or price."""

from dataclasses import dataclass

from app.agent_runtime.domain.usage import Pricing

EFFORTS = ("none", "low", "medium", "high")
MODES = ("STRUCTURED_MULTI_PATCH", "BOUNDED_AGENTIC")


@dataclass(frozen=True)
class ModelPolicy:
    provider: str
    model: str
    role: str
    allowed_modes: tuple[str, ...] = MODES
    default_effort: str = "medium"
    max_effort: str = "medium"
    experimental: bool = False

    def __post_init__(self) -> None:
        if (
            self.provider not in {"openai", "deepseek"}
            or not isinstance(self.model, str)
            or not self.model.strip()
            or len(self.model) > 255
        ):
            raise ValueError("Invalid bounded model route")
        if self.role not in {"planning", "investigation", "repair"}:
            raise ValueError("Unsupported routed role")
        if not self.allowed_modes or set(self.allowed_modes) - set(MODES):
            raise ValueError("Model routes are limited to bounded adaptive modes")
        if (
            self.default_effort not in EFFORTS
            or self.max_effort not in EFFORTS
            or EFFORTS.index(self.default_effort) > EFFORTS.index(self.max_effort)
        ):
            raise ValueError("Invalid model reasoning ceiling")
        if type(self.experimental) is not bool:
            raise TypeError("Experimental routing must be boolean")
        if self.provider == "deepseek" and not self.experimental:
            raise ValueError("DeepSeek routing must be explicitly experimental")


@dataclass(frozen=True)
class PricedModel:
    policy: ModelPolicy
    pricing: Pricing
    pricing_id: str
