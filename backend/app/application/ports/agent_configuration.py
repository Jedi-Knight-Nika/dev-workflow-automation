from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AgentConfigCommand:
    role: str
    enabled: bool
    provider: str
    model: str
    configuration: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentView:
    role: str
    enabled: bool
    provider: str
    model: str
    configuration: dict[str, Any]
    updated_at: datetime
    status: str
    active_jobs: int = 0
    total_runs: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_estimated_cost_usd: float = 0
    last_run_at: datetime | None = None
    last_duration_ms: int | None = None
    last_provider: str | None = None
    last_model: str | None = None


class AgentConfigurationWorkflow(Protocol):
    async def list(self) -> list[AgentView]: ...
    async def update(self, command: AgentConfigCommand) -> AgentView: ...
