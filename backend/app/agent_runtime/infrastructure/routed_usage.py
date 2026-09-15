"""Validate and price each routed purchase against the controller's admitted catalog."""

from decimal import Decimal
from typing import Any

from app.agent_runtime.domain.usage import Pricing, Usage
from app.agent_runtime.infrastructure.models import PricingCatalog


def settled_cost(requests: Any, total: Usage, prices: dict[str, PricingCatalog]) -> Decimal | None:
    if not total.complete or not isinstance(requests, list) or len(requests) > 16:
        return None
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_write_input_tokens",
    )
    observed = dict.fromkeys(fields, 0)
    cost = Decimal(0)
    try:
        for request in requests:
            if not isinstance(request, dict) or not isinstance(request.get("usage"), dict):
                return None
            price = prices[request["pricing_id"]]
            if (price.provider, price.model) != (request["provider"], request["model"]):
                return None
            if request["usage"].get("provider_cost_usd") is not None:
                # Bounded routed requests are catalog-priced; provider totals are
                # neither required nor trusted as an alternative invoice source.
                return None
            usage = Usage(**request["usage"])
            amount = Pricing(
                price.input_per_million,
                price.output_per_million,
                price.cached_input_per_million,
                price.cache_write_per_million,
            ).calculate(usage)
            if amount is None:
                return None
            cost += amount
            for field in fields:
                observed[field] += getattr(usage, field)
    except (KeyError, TypeError, ValueError):
        return None
    return cost if all(observed[field] == getattr(total, field) for field in fields) else None
