from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.ports.model_validation import (
    ModelValidationGateway,
    ModelValidationResult,
    NodeModelValidationStore,
)


@dataclass(frozen=True, slots=True)
class NodeModelValidationView:
    node_id: str
    status: str
    message: str | None
    validated_at: datetime


class ValidateNodeModel:
    def __init__(self, store: NodeModelValidationStore, gateway: ModelValidationGateway) -> None:
        self._store = store
        self._gateway = gateway

    async def execute(self, node_id: str) -> NodeModelValidationView:
        configuration = await self._store.node_model(node_id)
        if configuration is None:
            raise ValueError("Workflow node not found")
        provider, model = configuration
        result = (
            await self._gateway.validate(provider, model)
            if model.strip()
            else ModelValidationResult("NOT_CONFIGURED", "Choose a model first")
        )
        validated_at = datetime.now(UTC)
        await self._store.record_model_validation(node_id, result, validated_at)
        return NodeModelValidationView(node_id, result.status, result.message, validated_at)
