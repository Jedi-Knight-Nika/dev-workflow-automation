import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession, PricingCatalog
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.platform.configuration.settings import Settings
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.supervisor.infrastructure.service import supervise
from tests.integration.test_enrollment_and_costs import scenario


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_supervisor_accounts_once_and_does_not_repurchase_failed_decision(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    price_id = uuid4()
    model = "supervisor-test-" + str(price_id)
    original_credentials = None
    changed_credentials = False
    try:
        async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
            async with postgres_session_factory.begin() as session:
                integration = await session.scalar(
                    select(Integration).where(Integration.provider_name == "openai")
                )
                assert integration
                original_credentials = integration.encrypted_credentials
                if not original_credentials:
                    integration.encrypted_credentials = cipher.encrypt("test-only")
                    changed_credentials = True
                session.add(
                    PricingCatalog(
                        id=price_id,
                        provider="openai",
                        model=model,
                        version="test",
                        input_per_million=Decimal("0.2"),
                        output_per_million=Decimal("1.2"),
                        cached_input_per_million=Decimal("0.02"),
                        effective_at=datetime.now(UTC),
                        source_url="test",
                    )
                )
                native = await session.scalar(
                    select(DeveloperSession).where(DeveloperSession.task_id == task_id)
                )
                assert native
                native_id = native.id
            jobs = SqlPhaseJobs(postgres_session_factory, "supervisor-test", 60)
            intake = await jobs.claim()
            assert intake
            await jobs.complete(intake, Action.START)
            lease = await jobs.claim()
            assert lease and await jobs.heartbeat(lease)
            calls = []
            decision = {
                "action": "DELEGATE_IMPLEMENTATION",
                "task_class": "STANDARD",
                "confidence": 0.95,
                "assessment": "Clear task",
                "execution_brief": "Search, edit, targeted check.",
                "acceptance_criteria": ["Preserve requirement"],
                "unresolved_items": [],
                "physical_object": "window container",
                "operations": ["move", "resize"],
                "preserve": ["terminal content"],
                "do_not_assume": ["content zoom"],
            }

            def respond(request: httpx.Request) -> httpx.Response:
                calls.append(request)
                return httpx.Response(
                    200,
                    json={
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "input_tokens_details": {"cached_tokens": 0},
                        },
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": json.dumps(decision) if valid else "invalid",
                                    }
                                ],
                            }
                        ],
                    },
                )

            client = httpx.AsyncClient
            monkeypatch.setattr(
                httpx,
                "AsyncClient",
                lambda **kw: client(**kw, transport=httpx.MockTransport(respond)),
            )
            settings = Settings(supervisor_model=model)
            if valid:
                first = await supervise(postgres_session_factory, settings, lease, native_id)
                assert first == await supervise(
                    postgres_session_factory, settings, lease, native_id
                )
            else:
                with pytest.raises(ValueError):
                    await supervise(postgres_session_factory, settings, lease, native_id)
                with pytest.raises(PhaseBlocked, match="already recorded"):
                    await supervise(postgres_session_factory, settings, lease, native_id)
            assert len(calls) == 1
            async with postgres_session_factory() as session:
                runs = list(await session.scalars(select(AIRun).where(AIRun.task_id == task_id)))
                assert len(runs) == 1
                assert runs[0].role_kind == "SUPERVISOR"
                assert runs[0].input_tokens == 100 and runs[0].calculated_cost_usd is not None
            if valid:
                decision.clear()
                decision.update({"directive": "CONTINUE", "message": "Continue focused work."})
                for sequence in (1, 2):
                    anomaly = {
                        "sequence": sequence,
                        "kind": "TOOL_FAILURE",
                        "detail": "fixture error",
                    }
                    result = await supervise(
                        postgres_session_factory, settings, lease, native_id, anomaly=anomaly
                    )
                    assert result.action == "CONTINUE"
                    await supervise(
                        postgres_session_factory, settings, lease, native_id, anomaly=anomaly
                    )
                assert len(calls) == 3  # intake + two unique anomalies, never repeated
                with pytest.raises(ValueError, match="bounded Supervisor"):
                    await supervise(
                        postgres_session_factory,
                        settings,
                        lease,
                        native_id,
                        anomaly={"sequence": 3},
                    )
                async with postgres_session_factory() as session:
                    runs = list(
                        await session.scalars(select(AIRun).where(AIRun.task_id == task_id))
                    )
                    assert len(runs) == 3 and all(
                        run.calculated_cost_usd is not None for run in runs
                    )
    finally:
        async with postgres_session_factory.begin() as session:
            if changed_credentials:
                integration = await session.scalar(
                    select(Integration).where(Integration.provider_name == "openai")
                )
                assert integration
                integration.encrypted_credentials = original_credentials
            await session.execute(delete(PricingCatalog).where(PricingCatalog.id == price_id))
