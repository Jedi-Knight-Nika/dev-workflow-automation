import asyncio
from time import monotonic
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.analytics.infrastructure.cache import CachedAnalyticsQueries


async def test_hot_cache_entry_survives_capacity_eviction():
    inner = AsyncMock()
    inner.dashboard.return_value = {}
    cache = CachedAnalyticsQueries(inner)
    cache.cache = {("dashboard", day, None): (monotonic(), {}) for day in range(128)}
    await cache.dashboard(0)
    await cache.dashboard(128)
    assert ("dashboard", 0, None) in cache.cache
    assert ("dashboard", 1, None) not in cache.cache


@pytest.mark.asyncio
async def test_fresh_cache_hit_does_not_wait_for_fill_lock():
    inner = AsyncMock()
    cache = CachedAnalyticsQueries(inner, max_concurrent_fills=1)
    cache.cache[("dashboard", 30, None)] = monotonic(), {"ready": True}
    async with cache.capacity:
        result = await asyncio.wait_for(cache.dashboard(30), timeout=1)
    assert result == {"ready": True}
    inner.dashboard.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_at_capacity_does_not_evict_unrelated_entry():
    inner = AsyncMock()
    inner.dashboard.return_value = {"refreshed": True}
    cache = CachedAnalyticsQueries(inner)
    expired = monotonic() - 21
    cache.cache = {("dashboard", day, None): (expired, {}) for day in range(128)}
    await cache.dashboard(30)
    assert len(cache.cache) == 128
    assert ("dashboard", 0, None) in cache.cache
    await cache.dashboard(128)
    assert len(cache.cache) == 128
    assert ("dashboard", 0, None) not in cache.cache


@pytest.mark.asyncio
async def test_concurrent_misses_share_one_fill_and_cache_none():
    inner = AsyncMock()
    started, release = asyncio.Event(), asyncio.Event()

    async def fill(*args):
        started.set()
        await release.wait()

    inner.task.side_effect = fill
    task_id = uuid4()
    cache = CachedAnalyticsQueries(inner)
    first = asyncio.create_task(cache.task(task_id))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        second = asyncio.create_task(cache.task(task_id))
        release.set()
        assert await asyncio.gather(first, second) == [None, None]
        assert await cache.task(task_id) is None
        inner.task.assert_awaited_once_with(task_id)
    finally:
        release.set()
        await first


@pytest.mark.asyncio
async def test_different_keys_fill_independently_and_cancelled_reader_does_not_cancel_shared_fill():
    inner = AsyncMock()
    started, release = asyncio.Event(), asyncio.Event()
    blocked_id, other_id = uuid4(), uuid4()

    async def fill(identifier):
        if identifier == blocked_id:
            started.set()
            await release.wait()
        return {"id": identifier}

    inner.task.side_effect = fill
    cache = CachedAnalyticsQueries(inner)
    first = asyncio.create_task(cache.task(blocked_id))
    second = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        second = asyncio.create_task(cache.task(blocked_id))
        assert await asyncio.wait_for(cache.task(other_id), timeout=1) == {"id": other_id}
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await second == {"id": blocked_id}
        assert inner.task.await_count == 2
        assert not cache.fills
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_fill_is_not_cached_and_can_be_retried():
    inner = AsyncMock()
    inner.task.side_effect = [ValueError("Unavailable"), {"ready": True}]
    cache = CachedAnalyticsQueries(inner)
    task_id = uuid4()
    with pytest.raises(ValueError, match="Unavailable"):
        await cache.task(task_id)
    assert not cache.fills
    assert await cache.task(task_id) == {"ready": True}
