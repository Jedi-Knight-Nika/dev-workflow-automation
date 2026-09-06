# Database migration guide

Alembic migration files are immutable deployment history. Do not combine, rename, reorder, or
edit a migration after it has been applied outside local development. Add a new migration instead.

## Migration map

| Revisions | Area |
| --- | --- |
| `0001`–`0007` | Foundation, control plane, providers, GitHub, workspaces, PRs, validation |
| `0008`–`0019` | Knowledge, review findings, workers, retries, cost, webhook delivery |
| `0020`–`0030` | Workflow graph, Tester, terminals, Teams, model and execution settings |
| `0031`–`0036` | Roles/Agents, task properties, security gateway, notifications, memory, routing |
| `0037`–`0041` | Query indexes, workflow revisions, archival, terminal ownership, settings |
| `0042` | Adaptive orchestration and task execution profiles |
| `0043`–`0044` | Role runtime profiles and built-in runtime defaults |
| `0045` | Failure state, retry categories, health registry, and circuit breakers |
| `0046` | Provider-neutral integration synchronization state |
| `0047` | Repository archival lifecycle |
| `0048` | Durable notification retry scheduling |

## Adding a migration

1. Use the next numeric prefix and a short purpose-based filename.
2. Keep schema changes focused on one subsystem.
3. Provide a safe downgrade, or document why a PostgreSQL operation is intentionally retained.
4. Add indexes for new foreign keys and hot lookup paths.
5. Validate with `alembic upgrade head` and the PostgreSQL integration suite.

Historical migrations can be replaced by a baseline only as a deliberate release operation after
every supported deployment has crossed the selected revision. This is not routine cleanup.
