.PHONY: sync dev lint format format-check typecheck test check lock

sync:
	uv sync --locked --all-extras

dev:
	uv run uvicorn app.main:app --reload --port 8000

lint:
	uv run ruff check app tests

format:
	uv run ruff check --fix app tests
	uv run ruff format app tests

format-check:
	uv run ruff format --check app tests

typecheck:
	uv run mypy app

test:
	SCHEDULER_ENABLED=false uv run pytest -q

check: lint format-check typecheck test

lock:
	uv lock

