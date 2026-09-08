"""Normalize a native receipt once for all paid roles."""

from datetime import UTC, datetime

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Pricing
from app.agent_runtime.infrastructure.models import AIRun, PricingCatalog


def apply_receipt(row: AIRun, receipt: TurnReceipt, price: PricingCatalog | None) -> None:
    usage = receipt.usage
    row.native_turn_id, row.native_session_id = receipt.native_turn_id, receipt.native_session_id
    row.artifact = receipt.summary[-8000:]
    row.input_tokens, row.output_tokens = usage.input_tokens, usage.output_tokens
    row.cache_read_tokens, row.cache_write_tokens = (
        usage.cache_read_input_tokens,
        usage.cache_write_input_tokens,
    )
    row.reasoning_tokens, row.usage_complete = usage.reasoning_tokens, usage.complete
    row.provider_cost_usd, row.raw_usage = usage.provider_cost_usd, receipt.raw_usage
    row.provider_duration_ms = receipt.provider_duration_ms
    if price is not None and (price.provider, price.model) == (row.provider, row.model):
        row.pricing_id = price.id
        row.calculated_cost_usd = Pricing(
            price.input_per_million,
            price.output_per_million,
            price.cached_input_per_million,
            price.cache_write_per_million,
        ).calculate(usage)
    row.finished_at, row.status = datetime.now(UTC), receipt.status.upper()


def known_no_inference(row: AIRun) -> None:
    from decimal import Decimal

    row.input_tokens = row.output_tokens = row.cache_read_tokens = row.cache_write_tokens = (
        row.reasoning_tokens
    ) = 0
    row.usage_complete = True
    row.calculated_cost_usd = Decimal(0)
    row.raw_usage = {"inference_started": False}
