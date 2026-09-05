.PHONY: setup dev-backend dev-frontend up down logs validate-real backup-production restore-production provision-worker-db rotate-credentials operational-check backend-lint backend-typecheck backend-test frontend-lint frontend-typecheck frontend-build frontend-e2e test lint typecheck format format-check check migrate lock

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

validate-real:
	@test -n "$(TASK_KEY)" || (echo "TASK_KEY is required, for example TASK_KEY=CIT-531" >&2; exit 1)
	python3 scripts/validate_real_workflow.py "$(TASK_KEY)" $(VALIDATE_ARGS)

operational-check:
	sh -n deploy/backup.sh deploy/restore.sh deploy/provision-worker-db.sh
	python3 -m py_compile scripts/validate_real_workflow.py scripts/rotate_credentials.py

rotate-credentials:
	@test -n "$(NEW_APP_SECRET_KEY)" || (echo "NEW_APP_SECRET_KEY is required" >&2; exit 1)
	NEW_APP_SECRET_KEY="$(NEW_APP_SECRET_KEY)" CONFIRM_CREDENTIAL_ROTATION="$(CONFIRM_CREDENTIAL_ROTATION)" docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm rotate-credentials $(ROTATE_ARGS)

backup-production:
	docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm backup

restore-production:
	@test -n "$(BACKUP_SET)" || (echo "BACKUP_SET is required" >&2; exit 1)
	BACKUP_SET="$(BACKUP_SET)" CONFIRM_RESTORE="$(CONFIRM_RESTORE)" docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm restore

provision-worker-db:
	docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm provision-worker-db

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

frontend-e2e:
	cd frontend && npm run test:e2e

format:
	$(MAKE) -C backend format
	cd frontend && npm run format

format-check:
	$(MAKE) -C backend format-check
	cd frontend && npm run format:check

check: lint format-check typecheck test operational-check
	$(MAKE) frontend-build

migrate:
	cd backend && uv run alembic upgrade head

lock:
	cd backend && uv lock
