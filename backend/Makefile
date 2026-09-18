.PHONY: sync dev lint format format-check typecheck test check lock

sync:
	uv sync --locked --all-extras

dev:
	uv run uvicorn app.main:app --reload --port 8000

lint:
	uv run ruff check . ../scripts

format:
	uv run ruff format . ../scripts

format-check:
	uv run ruff format --check . ../scripts

typecheck:
	uv run mypy app ../scripts/validate_real_workflow.py ../scripts/rotate_credentials.py

test:
	SCHEDULER_ENABLED=false uv run pytest -q

check: lint format-check typecheck test

lock:
	uv lock
