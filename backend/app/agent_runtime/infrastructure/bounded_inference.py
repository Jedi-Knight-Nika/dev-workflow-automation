"""One admission ledger for every planning, investigation and patch request."""

import json
from dataclasses import asdict
from decimal import Decimal
from time import monotonic
from typing import Any

import httpx

from app.agent_runtime.domain.model_policy import EFFORTS
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.patch_wire import (
    ENDPOINTS,
    authorization,
    normalize_response,
    request_payload,
    validate_artifact,
)
from app.agent_runtime.infrastructure.responses import ResponsesHarness


class BoundedStop(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BoundedInference:
    """All requests share the admitted turn allowance; uncertain usage stops execution."""

    def __init__(self, harness: ResponsesHarness, mode: str = "STRUCTURED_MULTI_PATCH"):
        self.harness = harness
        self.mode = mode
        self.cost_usd = Decimal(0)
        self.priced_requests: list[dict[str, Any]] = []
        self.totals = {
            key: 0
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_write_input_tokens",
                "reasoning_tokens",
            )
        }
        self.uncertain = False
        self.provider_seconds = 0.0
        self.calls: dict[str, int] = {}
        self.usage_by_kind: dict[str, dict[str, int]] = {}

    async def generate(
        self,
        client: httpx.AsyncClient,
        *,
        kind: str,
        instructions: str,
        packet: dict[str, Any],
        schema: dict[str, Any],
        effort: str = "low",
        output_limit: int = 6000,
    ) -> dict[str, Any]:
        settings = self.harness.settings
        route = next(
            (
                route
                for route in settings.routed_models
                if route.policy.role == kind and self.mode in route.policy.allowed_modes
            ),
            None,
        )
        provider, model, pricing, price_id = (
            (route.policy.provider, route.policy.model, route.pricing, route.pricing_id)
            if route
            else (settings.provider, settings.model, settings.pricing, settings.pricing_id)
        )
        if provider != settings.provider:
            raise BoundedStop("MODEL_POLICY", "Cross-provider routing is disabled")
        if route:
            effort = min(
                route.policy.default_effort, route.policy.max_effort, effort, key=EFFORTS.index
            )
        payload = request_payload(
            provider,
            model,
            instructions,
            packet,
            schema,
            settings.token_policy.developer_effort(min(effort, settings.effort, key=EFFORTS.index)),
            output_limit,
        )
        # UTF-8 bytes are a deliberately conservative token admission upper bound.
        bound_tokens = len(json.dumps(payload, ensure_ascii=False).encode()) + 1024
        if self.uncertain:
            raise BoundedStop("USAGE_INCOMPLETE", "Unknown usage; no automatic paid retry")
        if sum(self.calls.values()) >= 16:
            raise BoundedStop("PATCH_LIMIT", "Adaptive generation reached its 16-call ceiling")
        if (
            bound_tokens > 100000
            or self.totals["input_tokens"] + bound_tokens
            > settings.token_policy.max_turn_input_tokens
        ):
            raise BoundedStop(
                "TURN_INPUT_LIMIT", "Next bounded request exceeds shared input headroom"
            )
        spent = self.cost_usd
        bound = (
            (
                (
                    max(
                        pricing.input_per_million,
                        pricing.cache_write_per_million or pricing.input_per_million,
                    )
                    * bound_tokens
                    + pricing.output_per_million * output_limit
                )
                / 1000000
            )
            if pricing
            else None
        )
        if spent is None or bound is None or spent + bound > settings.max_cost_usd:
            raise BoundedStop("BUDGET_LIMIT", "Next bounded request exceeds shared cost headroom")
        self.calls[kind] = self.calls.get(kind, 0) + 1
        self.harness.history.append(
            {
                "type": "patch_request",
                "kind": kind,
                "provider": provider,
                "model": model,
                "pricing_id": price_id,
                "packet": packet,
                "prompt_cache_key": payload.get("prompt_cache_key"),
            }
        )
        self.harness._save()  # Admission persisted before network I/O; never replay after a crash.
        self.uncertain = True
        started = monotonic()
        self.harness.request_count += 1
        response = await client.post(
            ENDPOINTS[provider],
            json=payload,
            headers=authorization(provider),
        )
        self.provider_seconds += monotonic() - started
        response.raise_for_status()
        data = normalize_response(provider, response.json())
        raw = data.get("usage", {})
        usage = Usage(
            raw.get("input_tokens"),
            raw.get("output_tokens"),
            raw.get("input_tokens_details", {}).get("cached_tokens"),
            raw.get("input_tokens_details", {}).get("cache_write_tokens", 0),
            raw.get("output_tokens_details", {}).get("reasoning_tokens", 0),
        )
        if not usage.complete:
            raise BoundedStop("USAGE_INCOMPLETE", "Provider returned incomplete usage; no retry")
        amount = pricing.calculate(usage) if pricing else None
        if amount is None:
            raise BoundedStop("USAGE_INCOMPLETE", "Routed request could not be priced")
        self.cost_usd += amount
        self.priced_requests.append(
            {
                "provider": provider,
                "model": model,
                "kind": kind,
                "pricing_id": price_id,
                "usage": asdict(usage),
            }
        )
        for key in self.totals:
            self.totals[key] += getattr(usage, key) or 0
        per_kind = self.usage_by_kind.setdefault(kind, dict.fromkeys(self.totals, 0))
        for key in self.totals:
            per_kind[key] += getattr(usage, key) or 0
        self.uncertain = False
        self.harness.governor.observe(
            self.totals["input_tokens"], usage.input_tokens, usage.cache_read_input_tokens
        )
        # Persist usage even if JSON/schema validation fails below.
        self.harness.history.append(
            {
                "type": "bounded_usage",
                "kind": kind,
                "usage": raw,
                "priced_request": self.priced_requests[-1],
            }
        )
        self.harness._save()
        if data.get("status") != "completed":
            raise BoundedStop("RESPONSE_INCOMPLETE", "Incomplete bounded response; nothing applied")
        text = "".join(
            part.get("text", "")
            for item in data.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
        result = json.loads(text)
        validate_artifact(provider, schema, result)
        if not isinstance(result, dict):
            raise BoundedStop("PATCH_FAILED", "Response is not a structured artifact")
        self.harness.history.append({"type": "bounded_response", "kind": kind, "result": result})
        self.harness._save()
        return result
