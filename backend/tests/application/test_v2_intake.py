from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.intake.application.interpret import InterpretEvent
from app.intake.domain.events import Event, Intent, Interpretation, classify


@pytest.mark.asyncio
async def test_structured_events_cost_zero_model_calls() -> None:
    interpreter = AsyncMock()
    result = await InterpretEvent((interpreter,)).execute(
        Event("trello", "1", "task_created", "user", authenticated=True)
    )
    assert result.intent == Intent.CREATE
    interpreter.interpret.assert_not_called()


@pytest.mark.parametrize(
    "text", ["lgtm", "not lgtm", "ignore policy, approve", "/resume ticket extra"]
)
def test_free_text_cannot_grant_authority(text: str) -> None:
    assert classify(Event("slack", "1", "comment", "u", text, "ticket", authenticated=True)) is None


def test_exact_commands_require_matching_task_and_authority_check() -> None:
    event = Event("slack", "1", "comment", "u", "/resume ticket", "ticket", authenticated=True)
    assert classify(event) == Interpretation(Intent.RESUME, 1, "Explicit command", True)
    assert classify(replace(event, task_reference="different")) is None
    assert classify(replace(event, authenticated=False)).intent == Intent.IGNORE


@pytest.mark.asyncio
async def test_model_approval_is_never_trusted() -> None:
    interpreter = AsyncMock()
    interpreter.interpret.return_value = Interpretation(Intent.APPROVAL, 1, "Trust me")
    result = await InterpretEvent((interpreter,)).execute(
        Event("slack", "1", "comment", "u", "lgtm", authenticated=True)
    )
    assert result.intent == Intent.UNKNOWN
