from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engineering.infrastructure.task_models import Task
from app.interfaces.http.routes.tasks import router
from app.platform.persistence.session import get_session


@pytest.mark.asyncio
async def test_ticket_create_read_notes_and_receipts_use_current_schema_without_starting_work(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def session_override() -> AsyncIterator[AsyncSession]:
        async with postgres_session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = session_override
    task_id = None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post("/tasks", json={"title": "An HTTP draft", "estimate": 0.5})
            assert created.status_code == 201, created.text
            task_id = UUID(created.json()["id"])
            assert created.json()["status"] == "NEW" and created.json()["workspace_path"] is None
            detail = await client.get(f"/tasks/{task_id}")
            assert detail.status_code == 200 and detail.json()["estimate"] == 0.5
            for suffix in ("jobs", "runs", "validations"):
                response = await client.get(f"/tasks/{task_id}/{suffix}")
                assert response.status_code == 200 and response.json() == []
            note = await client.post(f"/tasks/{task_id}/messages", json={"body": "What happened?"})
            assert note.status_code == 201, note.text
            assert (await client.get(f"/tasks/{task_id}/jobs")).json() == []
            assert (await client.get(f"/tasks/{task_id}/metrics")).json()["attempts"] == 0
    finally:
        if task_id:
            async with postgres_session_factory.begin() as session:
                await session.execute(delete(Task).where(Task.id == task_id))
