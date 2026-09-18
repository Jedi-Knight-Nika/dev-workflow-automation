import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import delete, select, update

from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.lifecycle import record_transition
from app.platform.messaging.infrastructure.outbox import (
    NotificationOutbox,
    SqlEventOutbox,
    enqueue_task_wakeup,
)
from app.platform.persistence.registry import Task


@pytest_asyncio.fixture
async def notification_store(postgres_session_factory):
    factory = postgres_session_factory
    async with factory.begin() as session:
        await session.execute(delete(NotificationOutbox))
    try:
        yield factory, SqlEventOutbox(factory)
    finally:
        async with factory.begin() as session:
            await session.execute(delete(NotificationOutbox))


async def test_notifications_are_always_enqueued(notification_store):
    factory, outbox = notification_store
    task_id = uuid4()
    async with factory.begin() as session:
        enqueue_task_wakeup(session, task_id, 1)
    claim = await outbox.claim()
    assert claim.event.task_id == task_id and claim.event.revision == 1


async def test_lifecycle_and_notification_commit_or_rollback_together(notification_store):
    factory, outbox = notification_store
    task_id = uuid4()
    async with factory.begin() as session:
        session.add(Task(id=task_id, title="Atomic notifications"))
    try:
        async with factory() as session:
            await record_transition(
                session, task_id, Action.CANCEL, expected_version=1, actor="test"
            )
            assert await session.scalar(select(NotificationOutbox.id)) is not None
            await session.rollback()
        assert await outbox.claim() is None
        async with factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task.lifecycle_version == 1
            await record_transition(
                session, task_id, Action.CANCEL, expected_version=1, actor="test"
            )
        leased = await outbox.claim()
        assert leased.event.task_id == task_id and leased.event.revision == 2
    finally:
        async with factory.begin() as session:
            await session.execute(delete(Task).where(Task.id == task_id))


async def test_uncommitted_notifications_are_not_visible(notification_store):
    factory, outbox = notification_store
    async with factory() as session:
        enqueue_task_wakeup(session, uuid4(), 1)
        await session.flush()
        assert await outbox.claim() is None
        await session.commit()
    assert await outbox.claim() is not None


async def test_concurrent_dispatchers_claim_distinct_rows(notification_store):
    factory, outbox = notification_store
    async with factory.begin() as session:
        for revision in range(1, 5):
            enqueue_task_wakeup(session, uuid4(), revision)
    claims = await asyncio.gather(*(outbox.claim() for _ in range(8)))
    identifiers = [claim.event.event_id for claim in claims if claim]
    assert len(identifiers) == len(set(identifiers)) == 4


async def test_expired_claim_cannot_complete_new_owners_delivery(notification_store):
    factory, outbox = notification_store
    async with factory.begin() as session:
        enqueue_task_wakeup(session, uuid4(), 1)
    first = await outbox.claim()
    async with factory.begin() as session:
        await session.execute(
            update(NotificationOutbox).values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    second = await outbox.claim()
    assert first.event == second.event and first.token != second.token
    await outbox.published(first)
    await outbox.retry(first, "OldOwner")
    async with factory() as session:
        row = await session.get(NotificationOutbox, first.event.event_id)
        assert row.published_at is None and row.lease_token == second.token
        assert row.last_error is None
    await outbox.published(second)
    assert await outbox.claim() is None


async def test_retry_retains_identity_and_delays_next_claim(notification_store):
    factory, outbox = notification_store
    async with factory.begin() as session:
        enqueue_task_wakeup(session, uuid4(), 1)
    first = await outbox.claim()
    await outbox.retry(first, "TimeoutError")
    assert await outbox.claim() is None
    assert (await outbox.backlog())[0] == 1
    async with factory.begin() as session:
        row = await session.get(NotificationOutbox, first.event.event_id)
        assert row.last_error == "TimeoutError" and row.attempts == 1
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
    second = await outbox.claim()
    assert first.event == second.event


async def test_retention_never_removes_unpublished_work(notification_store):
    factory, outbox = notification_store
    async with factory.begin() as session:
        enqueue_task_wakeup(session, uuid4(), 1)
        enqueue_task_wakeup(session, uuid4(), 1)
    leased = await outbox.claim()
    await outbox.published(leased)
    async with factory.begin() as session:
        await session.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == leased.event.event_id)
            .values(published_at=datetime.now(UTC) - timedelta(days=8))
        )
    await outbox.prune()
    assert (await outbox.backlog())[0] == 1
    async with factory() as session:
        assert await session.get(NotificationOutbox, leased.event.event_id) is None
