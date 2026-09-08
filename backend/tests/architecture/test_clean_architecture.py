import ast
from pathlib import Path
from typing import Any

import pytest

from app.engineering.application.create_task import CreateTask, CreateTaskCommand
from app.engineering.domain.lifecycle import TaskStatus
from app.engineering.domain.task import Task

BACKEND_ROOT = Path(__file__).parents[2]


def imported_modules(source_path: Path) -> list[str]:
    """Inspect the module in `from x import y`, not just the symbol `y`."""
    tree = ast.parse(source_path.read_text())
    result: list[str] = []
    package = list(source_path.relative_to(BACKEND_ROOT).parts[:-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join([*prefix, *([node.module] if node.module else [])])
            result.append(module)
            result.extend(f"{module}.{alias.name}" for alias in node.names)
    return result


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
        CreateTaskCommand(title="  Isolate business rules  ", priority=2, start_work=True)
    )

    assert task.title == "Isolate business rules"
    assert task.status == TaskStatus.NEW
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
async def test_creation_is_free_unless_start_is_explicit() -> None:
    from app.interfaces.http.schemas.tasks import TaskCreate

    unit_of_work = FakeUnitOfWork()
    assert not TaskCreate(title="Draft task").start_work
    await CreateTask(unit_of_work).execute(CreateTaskCommand(title="Draft task"))  # type: ignore[arg-type]
    assert unit_of_work.jobs.enqueued == []
    assert unit_of_work.commits == 1


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


@pytest.mark.parametrize(
    "context",
    [
        "engineering",
        "agent_runtime",
        "delivery",
        "teams",
        "intake",
        "repositories",
        "observability",
        "analytics",
    ],
)
@pytest.mark.parametrize("layer", ["domain", "application"])
def test_inner_layers_are_framework_independent(context: str, layer: str) -> None:
    root = BACKEND_ROOT / "app" / context / layer
    for path in root.rglob("*.py"):
        for imported in imported_modules(path):
            assert imported.split(".")[0] not in {
                "fastapi",
                "sqlalchemy",
                "httpx",
                "pydantic",
                "openai_codex",
                "claude_agent_sdk",
            }, path
            assert not any(
                part in imported.split(".")
                for part in ("infrastructure", "interfaces", "bootstrap")
            ), path
            if layer == "domain":
                assert ".application" not in imported, path


def test_http_uses_ports_not_database_adapters():
    for path in (BACKEND_ROOT / "app/interfaces/http").rglob("*.py"):
        for imported in imported_modules(path):
            assert "infrastructure" not in imported.split("."), path
            assert not imported.startswith("sqlalchemy"), path


def test_adapters_never_import_http_contracts():
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        if "infrastructure" not in path.parts:
            continue
        assert not any("app.interfaces" in name for name in imported_modules(path)), path


def test_no_parallel_horizontal_runtime():
    root = BACKEND_ROOT / "app"
    for folder in [
        "domain",
        "application",
        "infrastructure",
        "services",
        "api",
        "schemas",
        "db",
        "providers",
        "integrations",
    ]:
        assert not list((root / folder).rglob("*.py")), folder


def test_schema_contains_only_current_context_entities():
    from app.platform.persistence import registry  # noqa: F401
    from app.platform.persistence.base import Base

    forbidden = {
        "workflow_definitions",
        "workflow_nodes",
        "ai_agents",
        "worker_runs",
        "repository_chunks",
        "repository_indexes",
        "task_memories",
        "roles",
    }
    assert not forbidden.intersection(Base.metadata.tables)
    assert {
        "tasks",
        "ai_runs",
        "developer_sessions",
        "team_agent_profiles",
        "task_phase_runs",
    }.issubset(Base.metadata.tables)
    assert not {"state", "execution_version", "workflow_id", "workflow_node_id"}.intersection(
        Base.metadata.tables["tasks"].columns.keys()
    )
