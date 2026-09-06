# Backend test layout

Tests are grouped by the architectural boundary they exercise:

- `domain/` — pure policies, state machines, schemas, and value objects.
- `application/` — use cases coordinated through ports and test doubles.
- `infrastructure/` — provider, Git, worker, persistence-adjacent, and runtime behavior.
- `api/` — HTTP routes and transport behavior.
- `integration/` — tests requiring real PostgreSQL or other external infrastructure.
- `architecture/` — source-level dependency and layering fitness checks.
- `conftest.py` — shared fixtures available to the entire suite.

Place a test at the narrowest boundary that can prove the behavior. A domain rule should not
require a database, and SQL behavior should not be simulated in a domain test. Related behavior
may share a test module; avoid both one giant test file and one file per tiny class.

Commands:

```bash
uv run pytest -q
RUN_DATABASE_INTEGRATION_TESTS=true uv run pytest -q tests/integration
```
