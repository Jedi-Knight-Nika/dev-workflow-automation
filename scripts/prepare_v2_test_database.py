"""Bootstrap disposable local test schema when pgvector is unavailable.

This is not a migration test. Never point it at an application database.
The excluded vector tables are unrelated to the V2 execution/delivery suites.
"""

import asyncio
import os

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401 - register SQLAlchemy models
from app.db.base import Base


async def main() -> None:
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if (
        url.host != "127.0.0.1"
        or url.port != 55439
        or url.username != "v2_test"
        or url.database != "postgres"
    ):
        raise ValueError("Only the disposable localhost:55439/v2_test test cluster is allowed")
    engine = create_async_engine(url)
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if not any(type(column.type).__module__.startswith("pgvector") for column in table.columns)
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    await engine.dispose()
    print(f"Created {len(tables)} non-vector test tables; migrations were not exercised")


if __name__ == "__main__":
    asyncio.run(main())
