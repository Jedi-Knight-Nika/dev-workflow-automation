from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelValidationResult:
    status: str
    message: str | None


class ModelValidationGateway(Protocol):
    async def validate(self, provider: str, model: str) -> ModelValidationResult: ...


class NodeModelValidationStore(Protocol):
    async def node_model(self, node_id: str) -> tuple[str, str] | None: ...

    async def record_model_validation(
        self, node_id: str, result: ModelValidationResult, validated_at: datetime
    ) -> None: ...
