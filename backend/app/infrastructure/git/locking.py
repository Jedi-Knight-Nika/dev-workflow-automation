import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_local_locks: dict[uuid.UUID, asyncio.Lock] = {}
_local_locks_guard = asyncio.Lock()


@asynccontextmanager
async def repository_lock(session: AsyncSession, repository_id: uuid.UUID) -> AsyncIterator[None]:
    """Serialize mutations of one shared Git cache without blocking other repositories."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"repository:{repository_id}"},
        )
        yield
        return

    async with _local_locks_guard:
        lock = _local_locks.setdefault(repository_id, asyncio.Lock())
    async with lock:
        yield
