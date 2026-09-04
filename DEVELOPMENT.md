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

## Continuous integration

`.github/workflows/ci.yml` runs backend and frontend quality checks. Protect `main`
with a GitHub branch ruleset that requires pull requests and the **Quality gate**
status check, and blocks force pushes and branch deletion.
