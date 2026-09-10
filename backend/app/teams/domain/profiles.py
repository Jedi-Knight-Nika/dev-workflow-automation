from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class RoleKind(StrEnum):
    INTERPRETER = "INTERPRETER"
    DEVELOPER = "DEVELOPER"
    THINKER = "THINKER"
    REVIEWER = "REVIEWER"


@dataclass(frozen=True)
class AgentProfile:
    role_kind: RoleKind
    display_name: str
    provider: str
    model: str
    harness: str | None = None
    effort: str = "medium"
    enabled: bool = True
    avatar: str = ""
    supplemental_instructions: str = ""
    soft_budget_usd: Decimal | None = None
    hard_budget_usd: Decimal | None = None
    prompt_version: str = "fixed"

    def __post_init__(self) -> None:
        if not self.display_name.strip() or len(self.display_name) > 120:
            raise ValueError("Display name must contain 1–120 characters")
        if not self.model.strip() or len(self.model) > 255:
            raise ValueError("A model is required")
        if len(self.supplemental_instructions) > 8000:
            raise ValueError("Supplemental instructions exceed 8000 characters")
        if self.role_kind in {RoleKind.DEVELOPER, RoleKind.INTERPRETER} and not self.enabled:
            raise ValueError("Required role profiles cannot be disabled")
        if self.role_kind == RoleKind.INTERPRETER:
            if self.harness is not None or self.provider not in {"ollama", "deepseek", "openai"}:
                raise ValueError("Interpreter must use a supported classification provider")
        elif self.harness in {"responses", "patch"}:
            if self.role_kind != RoleKind.DEVELOPER or self.provider != "openai":
                raise ValueError("Responses is available only for OpenAI Developer profiles")
        elif (self.harness, self.provider) not in {("codex", "openai"), ("claude", "anthropic")}:
            raise ValueError("Coding profiles require a matching supported harness/provider")
        if self.effort not in {"none", "low", "medium", "high"}:
            raise ValueError("Unsupported reasoning effort")
        for budget in (self.soft_budget_usd, self.hard_budget_usd):
            if budget is not None and (not budget.is_finite() or budget <= 0):
                raise ValueError("Budgets must be positive finite USD amounts")
        if (
            self.soft_budget_usd is not None
            and self.hard_budget_usd is not None
            and self.soft_budget_usd > self.hard_budget_usd
        ):
            raise ValueError("Soft budget cannot exceed hard budget")


def default_profiles() -> tuple[AgentProfile, ...]:
    return (
        AgentProfile(RoleKind.INTERPRETER, "Interpreter", "ollama", "qwen3:4b", effort="none"),
        AgentProfile(RoleKind.DEVELOPER, "Developer", "openai", "gpt-5.6-terra", "codex"),
        AgentProfile(RoleKind.THINKER, "Thinker", "openai", "gpt-5.6-sol", "codex", "high", False),
        AgentProfile(
            RoleKind.REVIEWER, "Reviewer", "openai", "gpt-5.6-terra", "codex", "high", False
        ),
    )
