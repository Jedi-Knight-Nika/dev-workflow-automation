.PHONY: setup dev-backend dev-frontend up down logs validate-real backup-production restore-production rotate-credentials operational-check backend-lint backend-typecheck backend-test frontend-lint frontend-typecheck frontend-build frontend-unit frontend-e2e test lint typecheck format format-check check migrate lock
.PHONY: desktop-lint desktop-check desktop-format desktop-format-check shared-format shared-format-check
.PHONY: shell-lint shell-format shell-format-check

setup:
	cd backend && uv sync --all-extras --locked
	cd frontend && npm install

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && API_URL=$${API_URL:-http://localhost:8000} npm run dev

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
	@for script in deploy/*.sh scripts/*.sh; do sh -n "$$script" || exit; done
	python3 -m py_compile scripts/validate_real_workflow.py scripts/rotate_credentials.py

rotate-credentials:
	@test -n "$(NEW_APP_SECRET_KEY)" || (echo "NEW_APP_SECRET_KEY is required" >&2; exit 1)
	NEW_APP_SECRET_KEY="$(NEW_APP_SECRET_KEY)" CONFIRM_CREDENTIAL_ROTATION="$(CONFIRM_CREDENTIAL_ROTATION)" docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm rotate-credentials $(ROTATE_ARGS)

backup-production:
	docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm backup

restore-production:
	@test -n "$(BACKUP_SET)" || (echo "BACKUP_SET is required" >&2; exit 1)
	BACKUP_SET="$(BACKUP_SET)" CONFIRM_RESTORE="$(CONFIRM_RESTORE)" docker compose --env-file deploy/.env -f deploy/compose.production.yaml --profile tools run --rm restore

test:
	$(MAKE) backend-test
	$(MAKE) frontend-unit

lint:
	$(MAKE) backend-lint
	$(MAKE) frontend-lint
	$(MAKE) desktop-lint
	$(MAKE) shell-lint

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

frontend-unit:
	cd frontend && npm run test:unit

format:
	$(MAKE) -C backend format
	$(MAKE) shared-format
	$(MAKE) desktop-format
	$(MAKE) shell-format

format-check:
	$(MAKE) -C backend format-check
	$(MAKE) shared-format-check
	$(MAKE) desktop-format-check
	$(MAKE) shell-format-check

shared-format:
	frontend/node_modules/.bin/prettier --ignore-path .gitignore --ignore-path .prettierignore --write .

shared-format-check:
	frontend/node_modules/.bin/prettier --ignore-path .gitignore --ignore-path .prettierignore --check .

desktop-lint:
	frontend/node_modules/.bin/eslint desktop/src eslint.config.mjs

desktop-check:
	cd desktop/src-tauri && cargo clippy --locked --all-targets -- -D warnings

desktop-format:
	cd desktop/src-tauri && cargo fmt --all

desktop-format-check:
	cd desktop/src-tauri && cargo fmt --all -- --check

shell-lint:
	shellcheck scripts/*.sh deploy/*.sh

shell-format:
	shfmt -i 2 -ci -w scripts/*.sh deploy/*.sh

shell-format-check:
	shfmt -i 2 -ci -d scripts/*.sh deploy/*.sh

check: lint format-check typecheck test operational-check
	$(MAKE) frontend-build
	$(MAKE) desktop-check

migrate:
	cd backend && uv run alembic upgrade head

lock:
	cd backend && uv lock
