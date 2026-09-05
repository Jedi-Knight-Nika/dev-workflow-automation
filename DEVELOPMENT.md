# Development Guide

## Requirements

- Docker with Docker Compose
- Python 3.12 and `uv` for host-based backend development
- Node.js 22 LTS for host-based frontend development

Dependencies are pinned in `backend/uv.lock` and `frontend/package-lock.json`.

## Setup

```bash
cp .env.example .env
make setup
```

For host-based backend development, PostgreSQL must be reachable separately and the
database URLs must use `localhost` instead of the Compose service hostname `postgres`.
The Compose database is intentionally not published to a host port because the
containerized backend accesses it through Docker's internal network.

Compose runs four services: PostgreSQL, the API, a dedicated scheduler/agent worker,
and the frontend. The API applies migrations and does not execute agent jobs. The worker
has the shared workspace volume, Git, process/memory limits, a read-only root filesystem,
and graceful shutdown handling.

```bash
make dev-backend
make dev-frontend
```

## Quality commands

```bash
make check
make lint
make typecheck
make test
make format-check
make format
```

Application-owned commands:

```bash
make -C backend lint
make -C backend format
make -C backend format-check
make -C backend typecheck
make -C backend test
make -C backend check

cd frontend
npm run lint
npm run lint:fix
npm run format
npm run format:check
npm run typecheck
npm run build
npm run check
```

## Configuration

The annotated `.env.example` is the source of truth for local configuration. Never
commit `.env` or real integration credentials.

## Backend architecture

New backend behavior follows an inward dependency rule:

```text
API / worker entrypoints -> application use cases -> domain
                              ^
                              |
                  infrastructure implements ports
```

- `app/domain` contains framework-free entities, value types, and business policies.
- `app/application` contains use cases and `Protocol` ports; it may depend on the domain
  but not FastAPI, SQLAlchemy, provider SDKs, Docker, or concrete integrations.
- `app/infrastructure` contains SQLAlchemy repositories/unit-of-work implementations and
  replaceable external adapters.
- `app/api` and workers are delivery adapters that validate transport data, resolve
  dependencies through `app/bootstrap`, invoke use cases, and translate results.

Prefer composition and constructor injection. Do not introduce generic base repositories,
service locators, framework imports in the domain, or inheritance solely to share code.
Legacy behavior is migrated one vertical workflow at a time under existing regression tests;
new business logic must not be added directly to route handlers.

### GitHub App installation

Create a GitHub App and set its Setup URL to the public backend callback:

```text
https://YOUR_DOMAIN/api/v1/github/app/callback
```

For local development, use a tunnel to port 8000 because GitHub must reach the callback.
In Integrations, select **GitHub App installation**, enter the App slug, numeric App ID,
and generated private key, then save. Select **Install app** to choose the account and
repositories on GitHub. The signed callback stores the returned installation ID in the
existing encrypted credential and verifies repository access before marking the
integration connected. `GITHUB_APP_RETURN_URL` controls the browser destination after
that callback; it is the frontend Integrations URL, not the GitHub callback URL.

## Real workflow validation

After configuring GitHub, Linear, all four agent models, and a real low-risk repository,
apply the configured Linear trigger to an issue and observe its complete persisted workflow:

```bash
make validate-real TASK_KEY=CIT-531
```

The default command stops safely at `READY_TO_MERGE`. To exercise the guarded merge and
verify the final Linear transition, opt in explicitly:

```bash
make validate-real TASK_KEY=CIT-531 VALIDATE_ARGS="--merge --require-repair"
```

`--require-repair` additionally proves that at least one internal, CI, or external-review
repair job occurred. The validator fails on human/context/failure terminal states, missing
agent roles, missing PR evidence, timeout, or a merged task without a persisted Linear
Ready for Testing confirmation.

## Continuous integration

`.github/workflows/ci.yml` runs backend and frontend quality checks. Protect `main`
with a GitHub branch ruleset that requires pull requests and the **Quality gate**
status check, and blocks force pushes and branch deletion.

## Server deployment

The production stack keeps PostgreSQL, FastAPI, and SvelteKit off public host ports.
Caddy is the only ingress and obtains HTTPS certificates for `DOMAIN` automatically.
The scheduler uses the Docker Engine socket to launch a fresh constrained container for
each agent job. Job containers receive only their job ID as launch data, the database
and encryption settings required to load durable state, and the workspace volume. The
unused synchronous database URL and all webhook signing secrets are excluded. Set
`WORKER_DATABASE_URL` to a dedicated PostgreSQL login whose grants are limited to the
tables and operations required by agent jobs; production Compose requires this value.
They
run with a read-only root filesystem, dropped Linux capabilities, no-new-privileges,
explicit open-file, CPU, memory, PID, and temporary-filesystem limits, and privileged
mode disabled, then are removed.
Create a deployment environment file with strong, unique production values, then run
from the repository root:

```bash
cp deploy/.env.example deploy/.env
docker compose --env-file deploy/.env -f deploy/compose.production.yaml up -d postgres backend
make provision-worker-db
docker compose --env-file deploy/.env -f deploy/compose.production.yaml up -d --build
```

Production startup rejects blank, short, placeholder, or reused application/webhook
secrets. The three values must each be at least 32 characters and different from one
another. It also rejects placeholder database URLs and requires an absolute HTTPS
`GITHUB_APP_RETURN_URL`; `deploy/.env.example` is intentionally not runnable unchanged.

The first command starts PostgreSQL and applies Alembic migrations through the backend.
The second idempotently creates or rotates the disposable-job login and grants table
reads plus only the task/repository updates and worker-run inserts used by job code.
Run `make provision-worker-db` again after migrations that introduce tables workers
must read. Existing installations can adopt the restricted login with the same command.

DNS for `DOMAIN` must point to the server, and inbound TCP ports 80/443 plus UDP 443
must be allowed.

Create an on-host PostgreSQL/workspace backup set with:

```bash
make backup-production
```

Each timestamped directory contains a PostgreSQL custom-format dump, compressed
workspace archive, and SHA-256 manifest. The backup job validates both archives before
publishing the directory and deletes sets older than `BACKUP_RETENTION_DAYS`. Copy these
sets to separate storage; an on-host copy does not protect against server loss.

Restoration is destructive and requires an exact backup-set name plus an explicit
confirmation. Stop all application writers, restore, and restart the stack:

```bash
docker compose --env-file deploy/.env -f deploy/compose.production.yaml stop proxy frontend worker backend
make restore-production BACKUP_SET=20260905T120000Z CONFIRM_RESTORE=RESTORE
docker compose --env-file deploy/.env -f deploy/compose.production.yaml up -d
```

The restore tool rejects paths, verifies `SHA256SUMS`, validates both archives, replaces
the database, and replaces workspace contents. Take a fresh backup before restoring.

Rotate the application credential-encryption key with API and worker processes stopped.
The first command is a rollback-only dry run; the second requires explicit confirmation:

```bash
docker compose --env-file deploy/.env -f deploy/compose.production.yaml stop proxy frontend worker backend
make rotate-credentials NEW_APP_SECRET_KEY='new-long-random-secret'
make rotate-credentials NEW_APP_SECRET_KEY='new-long-random-secret' ROTATE_ARGS=--apply CONFIRM_CREDENTIAL_ROTATION=ROTATE
```

Immediately replace `APP_SECRET_KEY` in `deploy/.env` with the same new value and restart
the stack. Rotation locks all credential rows, decrypts every record before changing any
record, and commits all replacements in one transaction. If the command fails, the old
key remains authoritative. Take a database backup before an applied rotation.

The scheduler is trusted infrastructure because access to the Docker socket is
host-level authority. Do not expose that socket to the API, frontend, or job containers.
Docker network isolation cannot provide provider-domain allowlists by itself; enforce
outbound domain policy at the host firewall. `WORKER_EGRESS_PROXY` configures HTTP(S)
proxy use inside disposable jobs, but the firewall must also prevent direct proxy
bypass. Keep PostgreSQL in `WORKER_NO_PROXY` so database traffic stays private.
