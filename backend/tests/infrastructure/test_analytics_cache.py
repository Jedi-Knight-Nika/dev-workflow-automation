import asyncio
from time import monotonic
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.analytics.infrastructure.cache import CachedAnalyticsQueries


@pytest.mark.asyncio
async def test_fresh_cache_hit_does_not_wait_for_fill_lock():
    inner = AsyncMock()
    cache = CachedAnalyticsQueries(inner)
    cache.cache[("dashboard", 30, None)] = monotonic(), {"ready": True}
    async with cache.lock:
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
