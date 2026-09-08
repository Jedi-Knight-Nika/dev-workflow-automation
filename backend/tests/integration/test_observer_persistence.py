from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.observability.observer.domain import Attention, Scope
from app.observability.observer.models import ObserverConversation, ObserverEvent
from app.observability.observer.persistence import SqlObserverStore


async def test_observer_hold_dedupe_snooze_resolution_and_conversation_scope(
    postgres_session_factory,
):
    store = SqlObserverStore(postgres_session_factory)
    now = datetime.now(UTC)
    owner, fingerprint = uuid4().hex, "acceptance:" + uuid4().hex
    item = Attention(
        fingerprint,
        "HOST_MEMORY_PRESSURE",
        "WARNING",
        "Measured pressure",
        {"measured": 90},
        "TEST_ONLY",
        hold_seconds=300,
    )
    try:
        await store.synchronize([item], {"TEST_ONLY"}, now.isoformat())
        assert not any(e["title"] == "Measured pressure" for e in await store.events(Scope()))
        for seconds in (60, 120, 180, 240, 300):
            await store.synchronize(
                [item], {"TEST_ONLY"}, (now + timedelta(seconds=seconds)).isoformat()
            )
        events = [e for e in await store.events(Scope()) if e["title"] == "Measured pressure"]
        assert len(events) == 1
        assert await store.event_action(events[0]["id"], "snooze", 15)
        assert (
            next(e for e in await store.events(Scope()) if e["id"] == events[0]["id"])["status"]
            == "SNOOZED"
        )
        await store.synchronize([], set(), now.isoformat())
        assert any(e["id"] == events[0]["id"] for e in await store.events(Scope()))
        await store.synchronize([], {"TEST_ONLY"}, now.isoformat())
        assert not any(e["id"] == events[0]["id"] for e in await store.events(Scope()))
        question = await store.create_question(owner, Scope(), "What is happening?", None)
        assert await store.question("different-browser", question["request_id"]) is None
        with pytest.raises(LookupError):
            await store.create_question(
                owner, Scope("TEAM", team_id=str(uuid4())), "escape", question["conversation_id"]
            )
        with pytest.raises(LookupError):
            await store.history("different-browser", question["conversation_id"])
    finally:
        async with postgres_session_factory() as session, session.begin():
            await session.execute(
                delete(ObserverEvent).where(ObserverEvent.fingerprint == fingerprint)
            )
            await session.execute(
                delete(ObserverConversation).where(ObserverConversation.owner == owner)
            )
