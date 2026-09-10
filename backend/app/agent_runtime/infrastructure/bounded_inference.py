"""One admission ledger for every planning, investigation and patch request."""

import json
import os
from time import monotonic
from typing import Any

import httpx

from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.responses import ResponsesHarness, measured_usage


class BoundedStop(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BoundedInference:
    """All requests share the admitted turn allowance; uncertain usage stops execution."""

    def __init__(self, harness: ResponsesHarness):
        self.harness = harness
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
        payload = {
            "model": settings.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": json.dumps(packet, ensure_ascii=False)}],
            "store": False,
            "reasoning": {"effort": settings.token_policy.developer_effort(effort)},
            "text": {"verbosity": "low", "format": schema},
            "max_output_tokens": output_limit,
        }
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
        pricing = settings.pricing
        spent = pricing.calculate(measured_usage(self.totals)) if pricing else None
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
        self.harness.history.append({"type": "patch_request", "kind": kind, "packet": packet})
        self.harness._save()  # Admission persisted before network I/O; never replay after a crash.
        self.uncertain = True
        started = monotonic()
        response = await client.post(
            "https://api.openai.com/v1/responses",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        )
        self.provider_seconds += monotonic() - started
        response.raise_for_status()
        data = response.json()
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
        self.harness.history.append({"type": "bounded_usage", "kind": kind, "usage": raw})
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
        if not isinstance(result, dict):
            raise BoundedStop("PATCH_FAILED", "Response is not a structured artifact")
        self.harness.history.append({"type": "bounded_response", "kind": kind, "result": result})
        self.harness._save()
        return result
