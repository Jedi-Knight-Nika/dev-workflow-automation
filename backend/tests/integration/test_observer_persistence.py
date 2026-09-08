from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.observability.observer.domain import Attention, Scope
from app.observability.observer.models import (
    ObserverConversation,
    ObserverEvent,
    ObserverModelRun,
    ObserverPreference,
    ObserverQuestion,
)
from app.observability.observer.persistence import SqlObserverStore


async def test_preference_reads_do_not_write_and_rename_preserves_disabled_state(
    postgres_session_factory,
):
    store = SqlObserverStore(postgres_session_factory)
    owner = uuid4().hex
    try:
        assert await store.preference(owner) == {"focus": "normal", "last_seen_at": None}
        async with postgres_session_factory() as session:
            assert await session.get(ObserverPreference, owner) is None
        await store.preference(owner, {"enabled": False})
        await store.preference(owner, {"display_name": "Friday"})
        await store.preference(
            owner,
            {
                "local_ai_enabled": True,
                "model": "qwen3.5:2b",
                "memory_reserve_mb": 1024,
                "output_tokens": 256,
                "response_timeout_seconds": 30,
            },
        )
        value = await store.preference(owner)
        assert value["enabled"] is False
        assert value["display_name"] == "Friday"
        assert value["local_ai_enabled"] is True
        assert value["model"] == "qwen3.5:2b"
        assert value["memory_reserve_mb"] == 1024
        # The read works even inside a genuinely read-only PostgreSQL transaction.
        async with postgres_session_factory() as session:
            from sqlalchemy import text

            await session.execute(text("SET TRANSACTION READ ONLY"))
            row = await session.get(ObserverPreference, owner)
            assert row.values["display_name"] == "Friday"
    finally:
        async with postgres_session_factory() as session, session.begin():
            await session.execute(
                delete(ObserverPreference).where(ObserverPreference.owner == owner)
            )


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


async def test_crashed_local_receipt_is_recovered_without_fabricating_usage(
    postgres_session_factory,
):
    store = SqlObserverStore(postgres_session_factory)
    owner = uuid4().hex
    try:
        question = await store.create_question(owner, Scope(), "Recovery test", None)
        await store.receipt(
            question["request_id"],
            {"status": "STARTED", "prompt_eval_count": None, "eval_count": None},
        )
        async with postgres_session_factory() as session, session.begin():
            from sqlalchemy import select

            row = await session.get(ObserverQuestion, UUID(question["request_id"]))
            row.status = "INTERRUPTED"
            receipt = await session.scalar(
                select(ObserverModelRun).where(ObserverModelRun.question_id == row.id)
            )
            receipt.created_at = datetime.now(UTC) - timedelta(minutes=10)
        await store.cleanup()
        async with postgres_session_factory() as session:
            receipt = await session.scalar(
                select(ObserverModelRun).where(ObserverModelRun.question_id == row.id)
            )
            assert receipt.receipt["status"] == "INTERRUPTED"
            assert receipt.receipt["prompt_eval_count"] is None
            assert receipt.receipt["eval_count"] is None
    finally:
        async with postgres_session_factory() as session, session.begin():
            await session.execute(
                delete(ObserverConversation).where(ObserverConversation.owner == owner)
            )
