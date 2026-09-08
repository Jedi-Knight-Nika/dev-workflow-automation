# Autonomous Engineering Worker

A single-operator engineering control center: scoped tasks become code through a persistent native coding session, isolated validation, pull requests, review feedback and guarded merge.

The workflow is fixed. Models write and reason; deterministic application code owns authorization, scheduling, cost admission, publication and merge.

## Start here

- [Architecture and feature reference](PRODUCT.md)
- [How task execution and token accounting work](docs/v2-implementation.md)
- [Fresh database and deployment setup](docs/initial-setup.md)
- [First bounded native-agent smoke test](docs/first-task-smoke-test.md)
- [Development, tests and operational checks](DEVELOPMENT.md)
- [Refactor verification and remaining acceptance checks](docs/refactor-verification.md)
- [Design specification](autonomous_engineering_worker_v2_technical_architecture.md)

For local API/UI development, copy `.env.example`, configure secrets and use a new PostgreSQL database:

```sh
docker compose up --build postgres backend frontend
```

This does not enable paid execution. Native runners require the deployment overlay, configured dependency image, provider access, validated pricing and explicit Team budgets.

The implementation is covered by local backend/PostgreSQL/frontend/browser tests. Real Docker/native-model acceptance and representative paid-task benchmarks must be performed on the deployment host before unattended use. No percentage cost saving is claimed without those measurements.
