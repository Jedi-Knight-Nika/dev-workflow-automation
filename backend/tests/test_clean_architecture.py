import ast
from pathlib import Path
from typing import Any

import pytest

from app.application.tasks import CreateTask, CreateTaskCommand
from app.domain.tasks import Task, TaskState


class FakeTasks:
    def __init__(self) -> None:
        self.added: list[Task] = []

    async def add(self, task: Task) -> None:
        self.added.append(task)


class FakeJobs:
    def __init__(self) -> None:
        self.enqueued: list[tuple[Task, dict[str, Any]]] = []

    async def enqueue_intake(self, task: Task, payload: dict[str, Any]) -> object:
        self.enqueued.append((task, payload))
        return task.id


class FakeEvents:
    def __init__(self) -> None:
        self.added: list[tuple[object, str, dict[str, Any], str]] = []

    async def add(
        self,
        task_id: object,
        event_type: str,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> None:
        self.added.append((task_id, event_type, payload, source))


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.tasks = FakeTasks()
        self.jobs = FakeJobs()
        self.events = FakeEvents()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_create_task_use_case_coordinates_domain_through_ports() -> None:
    unit_of_work = FakeUnitOfWork()

    task = await CreateTask(unit_of_work).execute(  # type: ignore[arg-type]
        CreateTaskCommand(title="  Isolate business rules  ", priority=2)
    )

    assert task.title == "Isolate business rules"
    assert task.state == TaskState.NEW
    assert unit_of_work.tasks.added == [task]
    assert unit_of_work.jobs.enqueued == [(task, {"source": "dashboard"})]
    assert unit_of_work.events.added[0][1:] == (
        "TASK_CREATED",
        {"title": "Isolate business rules"},
        "api",
    )
    assert unit_of_work.commits == 1
    assert unit_of_work.rollbacks == 0


@pytest.mark.asyncio
async def test_create_task_use_case_rolls_back_as_one_transaction() -> None:
    unit_of_work = FakeUnitOfWork()

    async def fail(_: Task) -> None:
        raise RuntimeError("database unavailable")

    unit_of_work.tasks.add = fail
    with pytest.raises(RuntimeError, match="database unavailable"):
        await CreateTask(unit_of_work).execute(  # type: ignore[arg-type]
            CreateTaskCommand(title="Task")
        )

    assert unit_of_work.commits == 0
    assert unit_of_work.rollbacks == 1


def test_domain_layer_has_no_framework_or_infrastructure_imports() -> None:
    domain_root = Path(__file__).parents[1] / "app" / "domain"
    forbidden = {
        "fastapi",
        "sqlalchemy",
        "httpx",
        "pydantic",
        "app.application",
        "app.infrastructure",
    }

    for source_path in domain_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(
            imported == forbidden_name or imported.startswith(f"{forbidden_name}.")
            for imported in imports
            for forbidden_name in forbidden
        ), f"{source_path} imports outside the domain boundary"


def test_application_layer_has_no_transport_or_infrastructure_imports() -> None:
    application_root = Path(__file__).parents[1] / "app" / "application"
    forbidden = {
        "fastapi",
        "sqlalchemy",
        "httpx",
        "pydantic",
        "app.api",
        "app.bootstrap",
        "app.db",
        "app.infrastructure",
        "app.integrations",
        "app.services",
    }

    for source_path in application_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(
            imported == forbidden_name or imported.startswith(f"{forbidden_name}.")
            for imported in imports
            for forbidden_name in forbidden
        ), f"{source_path} imports an outer-layer dependency"


def test_legacy_service_namespace_stays_empty() -> None:
    services_root = Path(__file__).parents[1] / "app" / "services"

    assert not list(services_root.glob("*.py")), (
        "Place business rules in domain/application and external implementations in infrastructure"
    )


def test_transport_schemas_do_not_import_persistence_models() -> None:
    schemas_path = Path(__file__).parents[1] / "app" / "schemas.py"
    tree = ast.parse(schemas_path.read_text())
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert not any(name == "app.db" or name.startswith("app.db.") for name in imports)


def test_http_routes_depend_on_application_ports_not_persistence_adapters() -> None:
    api_root = Path(__file__).parents[1] / "app" / "api"
    forbidden = {"sqlalchemy", "app.db", "app.integrations", "app.infrastructure.persistence"}

    for source_path in api_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(
            imported == forbidden_name or imported.startswith(f"{forbidden_name}.")
            for imported in imports
            for forbidden_name in forbidden
        ), f"{source_path} couples HTTP transport to a persistence adapter"
