from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from app.agent_runtime.application.harness import HarnessSettings


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "resume"])
async def test_login_precedes_session_and_uses_process_only_credentials(
    tmp_path: Path, monkeypatch, operation: str
) -> None:
    sdk = pytest.importorskip("openai_codex")
    from app.agent_runtime.infrastructure.codex import CodexHarness

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    client = AsyncMock()
    with patch.object(sdk, "AsyncCodex", return_value=client) as factory:
        harness = CodexHarness(HarnessSettings("model", tmp_path, "contract"))
        if operation == "start":
            await harness.start()
        else:
            await harness.resume("saved-thread")
    assert client.mock_calls[0] == call.login_api_key("fixture-key")
    assert client.mock_calls[1][0] == f"thread_{operation}"
    config = factory.call_args.args[0]
    assert config.config_overrides == ('cli_auth_credentials_store="ephemeral"',)
    assert "fixture-key" not in repr(config)


@pytest.mark.asyncio
async def test_missing_key_stops_before_native_operations(tmp_path: Path, monkeypatch) -> None:
    sdk = pytest.importorskip("openai_codex")
    from app.agent_runtime.infrastructure.codex import CodexHarness

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = AsyncMock()
    with patch.object(sdk, "AsyncCodex", return_value=client):
        harness = CodexHarness(HarnessSettings("model", tmp_path, "contract"))
        with pytest.raises(ValueError, match="injected OpenAI API key"):
            await harness.start()
        with pytest.raises(ValueError, match="injected OpenAI API key"):
            await harness.resume("saved-thread")
    assert not client.mock_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "info,code",
    [
        ("unauthorized", "PROVIDER_AUTHENTICATION_FAILED"),
        ({"httpConnectionFailed": {"httpStatusCode": 401}}, "PROVIDER_AUTHENTICATION_FAILED"),
        ("usageLimitExceeded", "PROVIDER_RATE_LIMIT"),
        (None, "NATIVE_TURN_FAILED"),
    ],
)
async def test_failed_turn_preserves_safe_error_without_inventing_usage(
    tmp_path: Path, info, code: str
) -> None:
    sdk = pytest.importorskip("openai_codex")
    from openai_codex.generated.v2_all import TurnCompletedNotification

    from app.agent_runtime.infrastructure.codex import CodexHarness
    from app.agent_runtime.infrastructure.models import AIRun
    from app.agent_runtime.infrastructure.receipts import apply_receipt

    completed = TurnCompletedNotification.model_validate(
        {
            "threadId": "thread",
            "turn": {
                "id": "failed-turn",
                "items": [],
                "status": "failed",
                "error": {
                    "message": "Provider request contains secret-fixture and prompt text",
                    "codexErrorInfo": info,
                },
            },
        }
    )

    async def stream():
        yield SimpleNamespace(payload=completed)

    with patch.object(sdk, "AsyncCodex", return_value=AsyncMock()):
        harness = CodexHarness(HarnessSettings("model", tmp_path, "contract"))
        harness.thread = SimpleNamespace(id="thread")
        harness.turn = SimpleNamespace(stream=stream)
        receipt = await harness._collect()
    assert receipt.status == "failed"
    assert receipt.failure_code == code
    assert receipt.summary == code
    assert not receipt.usage.complete
    assert "secret-fixture" not in repr(receipt)
    row = AIRun()
    apply_receipt(row, receipt, None)
    assert row.failure_code == code
    assert row.artifact == code
    assert row.calculated_cost_usd is None
