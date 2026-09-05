from datetime import datetime

import pytest

from app.application.ports.model_validation import ModelValidationResult
from app.application.validate_node_model import ValidateNodeModel


class Store:
    def __init__(self, configuration: tuple[str, str] | None) -> None:
        self.configuration = configuration
        self.recorded: tuple[str, ModelValidationResult, datetime] | None = None

    async def node_model(self, node_id: str) -> tuple[str, str] | None:
        return self.configuration

    async def record_model_validation(
        self, node_id: str, result: ModelValidationResult, validated_at: datetime
    ) -> None:
        self.recorded = node_id, result, validated_at


class Gateway:
    async def validate(self, provider: str, model: str) -> ModelValidationResult:
        assert (provider, model) == ("anthropic", "claude-test")
        return ModelValidationResult("AVAILABLE", "available")


@pytest.mark.asyncio
async def test_validate_node_model_records_provider_result() -> None:
    store = Store(("anthropic", "claude-test"))
    result = await ValidateNodeModel(store, Gateway()).execute("node-1")
    assert result.status == "AVAILABLE"
    assert store.recorded is not None
    assert store.recorded[0] == "node-1"


@pytest.mark.asyncio
async def test_validate_node_model_handles_empty_model_without_provider_call() -> None:
    store = Store(("openai", ""))
    result = await ValidateNodeModel(store, Gateway()).execute("node-1")
    assert result.status == "NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_validate_node_model_rejects_missing_node() -> None:
    with pytest.raises(ValueError, match="not found"):
        await ValidateNodeModel(Store(None), Gateway()).execute("missing")
