from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engineering.infrastructure.task_models import Task
from app.interfaces.http.routes.tasks import router
from app.platform.persistence.session import get_session
from app.teams.infrastructure.team_models import Team


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


@pytest.mark.asyncio
async def test_creation_replay_conflict_and_page_headers(postgres_session_factory):
    async def session_override():
        async with postgres_session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = session_override
    team_id = uuid4()
    title = f"http-pagination-{uuid4()}"
    async with postgres_session_factory.begin() as session:
        session.add(Team(id=team_id, name=title))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {"title": title, "team_id": str(team_id), "request_id": str(uuid4())}
            first = await client.post("/tasks", json=body)
            assert first.status_code == 201, first.text
            assert first.json()["team_id"] == str(team_id)
            replay = await client.post("/tasks", json=body)
            assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]
            conflict = await client.post("/tasks", json={**body, "start_work": True})
            assert conflict.status_code == 409, conflict.text
            second = await client.post("/tasks", json={**body, "request_id": str(uuid4())})
            assert second.status_code == 201, second.text
            filters = {"search": title, "limit": 1}
            page = await client.get("/tasks", params=filters)
            assert page.status_code == 200 and len(page.json()) == 1
            cursor = page.headers["x-next-cursor"]
            final = await client.get("/tasks", params={**filters, "cursor": cursor})
            assert final.status_code == 200 and len(final.json()) == 1
            assert final.json()[0]["id"] != page.json()[0]["id"]
            assert "x-next-cursor" not in final.headers
            invalid = await client.get("/tasks", params={**filters, "cursor": "!invalid"})
            assert invalid.status_code == 422, invalid.text
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.team_id == team_id))
            await session.execute(delete(Team).where(Team.id == team_id))
