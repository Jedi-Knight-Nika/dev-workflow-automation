.PHONY: sync dev lint format format-check typecheck test check lock

sync:
	uv sync --locked --all-extras

dev:
	uv run uvicorn app.main:app --reload --port 8000

lint:
	uv run ruff check app migrations tests ../scripts

format:
	uv run ruff check --fix app migrations tests ../scripts
	uv run ruff format app migrations tests ../scripts

format-check:
	uv run ruff format --check app migrations tests ../scripts

typecheck:
	uv run mypy app ../scripts/validate_real_workflow.py ../scripts/rotate_credentials.py

test:
	SCHEDULER_ENABLED=false uv run pytest -q

check: lint format-check typecheck test

lock:
	uv lock
