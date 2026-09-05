from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    system: str
    prompt: str
    max_output_tokens: int = 4096
    temperature: float | None = None
    reasoning_effort: str = "default"
    timeout_seconds: int = 120


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderModel:
    id: str
    display_name: str


class AIProvider(ABC):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @abstractmethod
    async def run(self, request: ProviderRequest) -> ProviderResponse: ...

    @abstractmethod
    async def list_models(self) -> list[ProviderModel]: ...

    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "structured_output_repair": True}
