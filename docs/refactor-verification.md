# Refactor verification record

Verified locally on 2026-09-08. This records tests, not a production acceptance claim.

## Passed

- Backend: 319 pytest tests, including PostgreSQL persistence and real ticket HTTP routes.
- Backend Ruff, formatting and strict mypy: passed (218 checked source/script files).
- Fresh initial schema/default entities: initialized and tested in a separate local PostgreSQL database.
- Frontend ESLint, Prettier, Svelte/TypeScript checks and production build: passed.
- Frontend unit tests: 32 passed.
- Chromium browser tests with mocked API: 4 passed.
- Base/production-overlay Compose configuration validation: passed without starting services.
- Backup/restore shell syntax checks and git diff whitespace checks: passed.

Browser coverage includes explicit start consent, zero estimates, concurrent worker refresh,
ticket actor/time/receipt visibility, responsive notes and fullscreen queue/milestones.

Backend coverage includes fixed phases, optional planning handoff, helper receipt/session
separation, read-only mounts, Team shutdown without deactivation, idempotent start, fair
claiming, source eligibility/dedup, same-session feedback, reservations and conditional merge.

## Environment and caveats

The database tests used PostgreSQL 15 on an isolated local port/database, not the application's
database. Deployment Compose specifies PostgreSQL 16; CI/deployment acceptance should use it.

The host reported Node 20.18.2. Checks/build/browser tests passed, but the project requires
Node 22.13+; use the supported version for deployment/CI. Dependency resolution reported
four low-severity advisories; no automatic force-upgrade was performed.

Pytest emitted one upstream Starlette/AnyIO deprecation warning. The frontend build emitted
dependency/empty-chunk notices, not application type errors.

Docker was stopped. Real container builds, Caddy runtime validation, native model sessions,
dependency-image execution, cancellation and backup/restore remain deployment smoke tests.
The 10–20-task paid completion/cost benchmark has not run. No measured cost-saving percentage
or provider-invoice accuracy claim follows from mocked SDK/HTTP tests.

## Data and actions

No application database reset, paid worker start, provider inference, push, PR creation or merge
was performed during verification. The test database was separate. Source/config removals are
recoverable from Git; the working-tree changes have not been committed.

## Handoff

Read [architecture and features](../PRODUCT.md), [execution/accounting logic](v2-implementation.md)
and [setup/operator requirements](initial-setup.md). Supply Docker, a new application database,
protected secrets, provider access and verified prices, explicit budgets, a tested dependency
image, validation commands and reviewer/CI policy before authorizing one low-risk real task.
