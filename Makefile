.PHONY: setup dev-backend dev-frontend up down logs backend-lint backend-typecheck backend-test frontend-lint frontend-typecheck frontend-build test lint typecheck format format-check check migrate lock

setup:
	cd backend && uv sync --all-extras --locked
	cd frontend && npm install

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	$(MAKE) backend-test

lint:
	$(MAKE) backend-lint
	$(MAKE) frontend-lint

typecheck:
	$(MAKE) backend-typecheck
	$(MAKE) frontend-typecheck

backend-lint:
	$(MAKE) -C backend lint

backend-typecheck:
	$(MAKE) -C backend typecheck

backend-test:
	$(MAKE) -C backend test

frontend-lint:
	cd frontend && npm run lint

frontend-typecheck:
	cd frontend && npm run typecheck

frontend-build:
	cd frontend && npm run build

format:
	$(MAKE) -C backend format
	cd frontend && npm run format

format-check:
	$(MAKE) -C backend format-check
	cd frontend && npm run format:check

check: lint format-check typecheck test
	$(MAKE) frontend-build

migrate:
	cd backend && uv run alembic upgrade head

lock:
	cd backend && uv lock
