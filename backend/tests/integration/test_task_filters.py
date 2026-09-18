from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.engineering.application.ports.task_queries import TaskListFilters
from app.engineering.infrastructure.queries import SqlAlchemyTaskQueries
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"project": " orbit "}, {"internal", "external", "split", "mixed"}),
        ({"team": " core "}, {"external", "split", "mixed"}),
        ({"provider": "internal", "project": "Orbit"}, {"internal"}),
        ({"provider": "internal", "team": "Core"}, set()),
        ({"provider": "linear", "team": "Core"}, {"external", "mixed"}),
        ({"provider": "linear", "team": "Core", "project": "Orbit"}, {"external", "mixed"}),
        ({"provider": "linear", "project": "Orbit"}, {"external", "split", "mixed"}),
        ({"team": "Other", "project": "Missing"}, set()),
    ],
)
async def test_project_and_team_filters_preserve_snapshot_scope(
    postgres_session_factory, filters, expected
):
    prefix = f"filters-{uuid4()}"
    tasks = {
        name: Task(
            id=uuid4(),
            title=f"{prefix}-{name}",
            project_name="Orbit" if name in {"internal", "archived"} else None,
            archived_at=datetime.now(UTC) if name == "archived" else None,
        )
        for name in ("internal", "external", "split", "mixed", "archived")
    }
    sources = [
        ("external", "linear", "Core", "Orbit"),
        ("split", "linear", "Other", "Other"),
        ("split", "trello", "Core", "Orbit"),
        ("mixed", "linear", "Core", "Other"),
        ("mixed", "trello", "Other", "Orbit"),
    ]
    async with postgres_session_factory.begin() as session:
        session.add_all(tasks.values())
        await session.flush()
        session.add_all(
            ExternalTaskSnapshot(
                task_id=tasks[name].id,
                provider=provider,
                external_id=str(uuid4()),
                identifier=name,
                raw_payload={"team": {"name": team}, "project": {"name": project}},
            )
            for name, provider, team, project in sources
        )
    try:
        async with postgres_session_factory() as session:
            views = await SqlAlchemyTaskQueries(session).list(
                100, TaskListFilters(search=prefix, **filters)
            )
            assert {view.task.id for view in views} == {tasks[name].id for name in expected}
            assert len(views) == len(expected)
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(
                delete(Task).where(Task.id.in_([task.id for task in tasks.values()]))
            )
