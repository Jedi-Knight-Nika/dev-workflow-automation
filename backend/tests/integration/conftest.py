import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def _integration_database_url() -> str | None:
    configured = os.getenv("TEST_DATABASE_URL")
    if configured is None and os.getenv("RUN_DATABASE_INTEGRATION_TESTS") == "true":
        configured = os.getenv("DATABASE_URL")
    if configured:
        return configured.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    if os.getenv("GITHUB_ACTIONS") == "true":
        return (
            "postgresql+asyncpg://engineering_worker:ci-password@localhost:5432/engineering_worker"
        )
    return None


@pytest_asyncio.fixture
async def postgres_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = _integration_database_url()
    if url is None:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    engine: AsyncEngine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
