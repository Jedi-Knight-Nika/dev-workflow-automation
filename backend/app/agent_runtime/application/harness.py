from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.domain.usage import Pricing, Usage


class WorkspaceUnavailable(RuntimeError):
    """The native runner cannot safely use its prepared task checkout."""


@dataclass(frozen=True)
class HarnessSettings:
    model: str
    workspace: Path
    instructions: str
    effort: str = "medium"
    max_turns: int = 40
    max_cost_usd: Decimal = Decimal(5)
    timeout_seconds: int = 1200
    pricing: Pricing | None = None
    read_only: bool = False
    token_policy: TokenEfficiencyPolicy = field(default_factory=TokenEfficiencyPolicy)
    progress_callback: Callable[[dict[str, Any]], None] | None = None
    progress_baseline: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workspace.is_absolute() or not self.model.strip():
            raise ValueError("Explicit workspace and model are required")
        if not 1 <= self.max_turns <= 200 or not 1 <= self.timeout_seconds <= 7200:
            raise ValueError("Invalid harness execution limits")
        if not self.max_cost_usd.is_finite() or self.max_cost_usd <= 0:
            raise ValueError("A positive finite cost budget is required")


@dataclass(frozen=True)
class TurnReceipt:
    native_session_id: str
    native_turn_id: str
    summary: str
    status: str
    usage: Usage
    raw_usage: dict[str, Any] = field(default_factory=dict)
    provider_duration_ms: int | None = None
    cumulative_usage: dict[str, int | None] | None = None
    failure_code: str | None = None
    token_efficiency: dict[str, Any] = field(default_factory=dict)


class DeveloperHarness(Protocol):
    async def start(self) -> str: ...
    async def resume(self, native_session_id: str) -> None: ...
    async def run_turn(self, prompt: str) -> TurnReceipt: ...
    async def compact(self) -> TurnReceipt: ...
    async def interrupt(self) -> None: ...
    async def inspect(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...
