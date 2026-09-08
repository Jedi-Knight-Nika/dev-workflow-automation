# Development and verification

## Requirements

Python 3.12 with uv, Node.js 22+, PostgreSQL and Docker Compose. Dependencies are locked in backend/uv.lock and frontend/package-lock.json.

Read [initial setup](docs/initial-setup.md) before enabling execution. Local API/UI work does not require paid workers.

## Host development

```sh
cd backend
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Point DATABASE_URL and DATABASE_URL_SYNC at a new development database. For frontend work:

```sh
cd frontend
npm ci
npm run dev
```

## Quality gates

```sh
make -C backend check
cd frontend
npm run check
npm run test:e2e
```

Backend check covers Ruff, formatting, mypy and pytest. Database integration tests require TEST_DATABASE_URL targeting an isolated initialized PostgreSQL database; without it those tests skip. Do not confuse skipped integration tests with verified persistence.

Browser tests start a local development server and mock control-plane responses. They check task creation/start consent, zero estimates, concurrent-worker refresh, ticket receipts/status history, and fullscreen queue visibility without provider calls.

CI additionally type-checks the operator scripts. The observer is read-only:

```sh
python scripts/validate_real_workflow.py TRELLO-example --poll-seconds 15
```

It waits for the fixed lifecycle and emits JSON evidence. It never performs merge or resume.

## Architecture rules

Business behavior belongs to its owning context: intake, engineering, agent_runtime, delivery, teams or repositories. Framework-free domain rules are consumed by application use cases and ports. Infrastructure implements persistence/container/provider boundaries. interfaces/http translates requests; bootstrap constructs adapters.

Do not add a parallel application-wide domain/application/infrastructure hierarchy. Do not make HTTP schemas the model for domain or adapter code. Do not add generic repositories or empty layers without a consumer. Existing architecture tests enforce forbidden dependency directions.

## Test levels and claims

1. Pure domain/application tests: transitions, admission, usage, classification and merge policies.
2. Adapter tests: HTTP/SDK/Docker protocol fakes, filesystem/Git checks, bounded output.
3. PostgreSQL tests: initial schema/defaults, lifecycle/audit, leases, costs, helpers, session changes, source dedup and outbox.
4. Frontend unit/build/browser tests: current contracts and operator actions.
5. Deployment acceptance: real container isolation, dependency image, native SDK start/resume/compaction/cancel and offline restore.
6. Authorized task benchmark: real source → code → tests → PR → review correction → merge, with actual cost and completion evidence.

Levels 5–6 require the deployment host and explicit spending authorization. Local passing tests do not establish provider invoice accuracy or an autonomous completion rate.

## Configuration and operational safety

Examples contain no valid credentials or prices. Do not commit .env, PEM files, native sessions or receipts containing sensitive data. Base Compose binds loopback only. Production proxy authentication protects console APIs; webhooks verify provider signatures.

Application startup creates the frozen initial schema only in an empty compatible database. Never stamp an incompatible schema or reset usage to evade budgets.

Build dependency images deliberately. Native coding has provider egress but no GitHub/DB credentials. Validation is offline. Git publication is deterministic and separate. Review waits and scheduler polling must not create inference requests.

See [PRODUCT.md](PRODUCT.md) for entity/feature ownership and [execution logic](docs/v2-implementation.md) for token accounting and recovery.
