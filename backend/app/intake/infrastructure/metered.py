"""Bounded interpretation outside event transactions, with durable cost admission."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.domain.usage import Pricing, Usage
from app.agent_runtime.infrastructure.models import AIRun, PricingCatalog
from app.agent_runtime.infrastructure.reservations import reserve_budget
from app.intake.domain.events import Event, Interpretation
from app.intake.infrastructure.cloud_wire import normalized_usage, request_body, response_text
from app.intake.infrastructure.models import LocalModelRun
from app.intake.infrastructure.ollama import (
    Classification,
    OllamaInterpreter,
    classification_messages,
)
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher


class MeteredLocalInterpreter:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        task_id: UUID,
        interpreter: OllamaInterpreter,
    ) -> None:
        self.sessions, self.task_id, self.interpreter = sessions, task_id, interpreter

    async def interpret(self, event: Event) -> Interpretation:
        started, status = monotonic(), "FAILED"
        try:
            result = await self.interpreter.interpret(event)
            status = "COMPLETED"
            return result
        finally:
            usage = self.interpreter.last_usage
            async with self.sessions.begin() as session:
                session.add(
                    LocalModelRun(
                        task_id=self.task_id,
                        model=self.interpreter.model,
                        status=status,
                        duration_ms=int((monotonic() - started) * 1000),
                        input_tokens=usage.get("prompt_eval_count"),
                        output_tokens=usage.get("eval_count"),
                    )
                )


class CloudInterpreter:
    """Optional fixed-endpoint cloud fallback. No tools/history/retries.

    Only explicitly configured models with verified standard-tier prices can run.
    Its conservative byte-sized input reservation plus output ceiling is admitted
    before HTTP. A lost response remains unknown; it is never a free retry.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        task_id: UUID,
        model: str,
        request_limit: Decimal,
        timeout: int = 30,
        *,
        role_budget: Decimal | None = None,
        role_kind: str = "INTERPRETER",
        messages: list[dict[str, str]] | None = None,
    ) -> None:
        provider, separator, name = model.partition("/")
        self.provider, self.model = (provider, name) if separator else ("openai", model)
        self.sessions, self.task_id = sessions, task_id
        self.request_limit, self.timeout = request_limit, timeout
        self.role_budget = role_budget
        if role_kind not in {"INTERPRETER", "SUPERVISOR"}:
            raise ValueError("Unsupported classification role")
        self.role_kind = role_kind
        self.messages = messages

    async def interpret(self, event: Event) -> Interpretation:
        messages = self.messages or classification_messages(event)
        url, payload = request_body(self.provider, self.model, messages)
        if self.role_kind == "SUPERVISOR" and self.provider == "openai":
            payload["reasoning"] = {"effort": "low"}
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "task_event_decision",
                    "strict": True,
                    "schema": Classification.model_json_schema(),
                }
            }
        async with self.sessions.begin() as session:
            price = await session.scalar(
                select(PricingCatalog)
                .where(
                    PricingCatalog.provider == self.provider,
                    PricingCatalog.model == self.model,
                    PricingCatalog.context_tier == "standard",
                    PricingCatalog.service_tier == "standard",
                    PricingCatalog.effective_at <= datetime.now(UTC),
                )
                .order_by(PricingCatalog.effective_at.desc())
                .limit(1)
            )
            integration = await session.scalar(
                select(Integration).where(Integration.provider_name == self.provider)
            )
            if price is None or integration is None or not integration.encrypted_credentials:
                raise ValueError(
                    "Fallback needs verified pricing and its configured provider integration"
                )
            pricing = Pricing(
                price.input_per_million,
                price.output_per_million,
                price.cached_input_per_million,
                price.cache_write_per_million,
            )
            # UTF-8 byte count plus ample framing allowance is intentionally not
            # advertised as a tokenizer estimate. Never reserve average tokens.
            reserve = pricing.calculate(Usage(len(json.dumps(messages).encode()) + 2048, 512, 0, 0))
            if reserve is None or not 0 < reserve <= self.request_limit:
                raise ValueError("Fallback exceeds its per-request USD allowance")
            await reserve_budget(
                session,
                self.task_id,
                reserve,
                role_kind=self.role_kind,
                role_budget=self.role_budget,
            )
            key = cipher.decrypt(integration.encrypted_credentials)
            run = AIRun(
                task_id=self.task_id,
                role_kind=self.role_kind,
                provider=self.provider,
                model=self.model,
                prompt_version="supervisor.review"
                if self.role_kind == "SUPERVISOR"
                else "interpreter.classification",
                status="RUNNING",
                reserved_cost_usd=reserve,
                pricing_id=price.id,
            )
            session.add(run)
            await session.flush()
            run_id = run.id
        started = monotonic()
        try:
            async with (
                asyncio.timeout(self.timeout),
                httpx.AsyncClient(
                    timeout=self.timeout, trust_env=False, follow_redirects=False
                ) as client,
                client.stream(
                    "POST",
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                ) as response,
            ):
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 32000:
                        raise ValueError("Oversized fallback response")
                    body.extend(chunk)
            data = json.loads(body)
            raw = data.get("usage") or {}
            usage = normalized_usage(self.provider, raw)
            # Save billing even if the classifier result is malformed or a refusal.
            async with self.sessions.begin() as session:
                row = await session.get(AIRun, run_id, with_for_update=True)
                assert row
                row.raw_usage, row.usage_complete = raw, usage.complete
                row.input_tokens, row.output_tokens = usage.input_tokens, usage.output_tokens
                row.cache_read_tokens, row.cache_write_tokens = (
                    usage.cache_read_input_tokens,
                    usage.cache_write_input_tokens,
                )
                row.reasoning_tokens = usage.reasoning_tokens
                row.calculated_cost_usd = pricing.calculate(usage)
                row.finished_at, row.status = datetime.now(UTC), "COMPLETED"
                row.provider_duration_ms = int((monotonic() - started) * 1000)
            text = response_text(self.provider, data)
            result = Classification.model_validate_json(text)
            return Interpretation(result.intent, result.confidence, result.reason)
        except BaseException as exc:
            async with self.sessions.begin() as session:
                row = await session.get(AIRun, run_id, with_for_update=True)
                if row and row.status == "RUNNING":
                    row.status, row.finished_at = "FAILED", datetime.now(UTC)
                    row.failure_code = type(exc).__name__[:100]
            if isinstance(exc, (httpx.HTTPError, KeyError, TypeError)):
                raise ConnectionError(
                    "Cloud interpretation unavailable; check metered run"
                ) from exc
            raise
