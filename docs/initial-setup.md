# V2 initial database and runtime setup

This branch is a **fresh-install baseline**, not an upgrade of the earlier MVP.
The old incremental migrations have been replaced by one initial revision,
`0001_initial`. This document takes precedence over older database-upgrade instructions.

The code change does not delete your application database, reset usage, start Docker,
or enable paid workers. A database reset is a separate, explicitly targeted operation.

## What the initial revision creates

`backend/migrations/initial_schema.sql` is a frozen PostgreSQL schema. The revision
executes it and `initial_entities.sql` in one transaction. It does not import current
ORM classes, call `create_all`, or reconstruct the database with column-add migrations.
Foreign keys, enum types, check constraints and query indexes are part of the snapshot.
Concurrent application starts serialize initialization with a PostgreSQL advisory lock.

| Entity | Initial state |
| --- | --- |
| Default team | Enabled, one concurrent task, no assigned repositories |
| Interpreter profile | Local Ollama / `qwen3:4b`; local interpretation still requires runtime opt-in |
| Developer profile | Codex / OpenAI / `gpt-5.6-terra`; no USD budget configured |
| Thinker and Reviewer profiles | Disabled; optional paid dispatch is not implemented yet |
| Team automation policy | Enrollment and auto-merge disabled; repository/reviewer/check lists empty |
| Account settings | Docker runtime, automatic repository indexing disabled |
| Integrations | GitHub, Linear, Trello, Slack, OpenAI, Anthropic and DeepSeek placeholders, no credentials |
| Tasks, jobs, AI runs, prices | Empty; no sample work or invented prices |

Creating another Team through the API creates its four fixed profiles and disabled
automation policy atomically. Reinitializing profiles only fills missing roles; it
does not overwrite operator configuration. No workflow graph is seeded.

**Schema-cleanup boundary:** the snapshot currently contains 55 ORM-managed tables.
Some are still used by shared ticket, notification, integration, audit and legacy-facing
API/read models. This is not yet a minimal V2-only table set. The scheduler no longer
dispatches legacy work, but those remaining code paths and their tables require separate
vertical removal. Dropping them now would break active readers. The old raw vector
`knowledge_chunks` table and pgvector extension are not included.

## Safe initialization

1. Keep the scheduler stopped. Preserve a backup if any existing database or workspace
   might still be useful. Do not run volume deletion commands as part of normal setup.
2. Create a **new, empty** PostgreSQL database or a separately named Docker volume.
   Configure `DATABASE_URL` and `DATABASE_URL_SYNC` for that same database.
3. From `backend`, with dependencies installed and those URLs configured, run:

   ```sh
   .venv/bin/alembic upgrade head
   .venv/bin/alembic current
   ```

   The expected revision is `0001_initial`. The API container performs the same upgrade
   on startup. Running it again at the current revision leaves rows and settings intact.
4. Open the UI and configure repositories/integrations, fixed Team profiles and verified
   model prices. Secrets belong in the existing encrypted integration flow, not profiles.
5. Build a repository-appropriate native runner image with its validation dependencies.
   Configure deterministic validation commands, allowed repository IDs and USD budgets.
6. Follow [the V2 deployment guide](v2-implementation.md#deployment). Check isolation,
   cancellation and native-session persistence before enabling one approved test task.

Do not use `alembic stamp head`, manually rewrite `alembic_version`, or point this
baseline at an MVP volume. A recognized old revision produces a retired-schema error;
an unversioned nonempty schema is also refused. Neither path automatically drops data.
Destructive downgrade is deliberately unsupported. Restore a backup into a separate
database or explicitly dispose of a verified scratch database instead.

The frozen snapshot represents this pre-release baseline. Future released schema
changes must be reviewed and versioned; do not silently edit a deployed baseline and
expect `upgrade head` to apply differences.

## Startup and execution controls

- Plain local and production Compose keep scheduling disabled. They are suitable for
  configuring the API/UI without launching model work.
- The V2 overlay exposes `V2_SCHEDULER_ENABLED=false` by default. Change it only after
  checking images, credentials, prices, per-task/Team policy, source scope and validation.
- `LEGACY_EXECUTOR=true` and `LEGACY_WORKFLOW_ROUTING=true` are rejected. Those flags do
  not revive the retired scheduler loops.
- `REPOSITORY_RAG_ENABLED=true` is rejected with the V2 lifecycle. This initial schema
  has no vector store. Native agents inspect current files; new tasks fetch the configured
  repository base branch rather than waiting for an index.
- Old `MAX_*_TOKENS` / proposal-loop settings are no longer deployment controls for the
  V2 lane. Configure actual USD limits on fixed profiles and Team automation policy.
- The disabled scheduler process waits for a shutdown signal instead of exiting into a
  container restart loop. Enabled scheduler shutdown cancels active phase coroutines and
  finishes their cancellation handling. API shutdown also cleans up after startup failure.
- Pausing or changing sessions does **not** erase recorded costs. Unknown-cost turns
  require reconciliation; restarting a service is not a budget reset.

The controller alone has database access and the Docker socket. Developer containers
have only their task checkout, native state and approved provider credentials. Validation
containers receive neither database/model credentials nor network access.

## Explicit model and harness changes

1. Pause the task and wait for its worker to stop and record its receipt.
2. Select the target model/harness in the Team's Developer profile.
3. Open the ticket's **Native Developer session** panel and refresh its state.
4. Choose either to keep the Codex thread or start a bounded new-session handoff.
   Provide an operator reason and apply the change.
5. Check the task and resume separately when ready. Applying the change makes no model
   call, does not edit files, and does not move the task to another workflow stage.

Keeping the thread is supported for Codex/OpenAI model changes: the next turn resumes
the same native ID using the chosen model. This follows the documented
[Codex thread-resume model override](https://learn.chatgpt.com/docs/app-server).
Other combinations conservatively require an explicit new native session. The app does
not promise that Claude and Codex histories are interchangeable.

A handoff keeps the same checkout and last known revision. It sends current requirements,
pending feedback, an operator note, and at most 4,000 characters of advisory checkpoint
summary, bounded to 24,000 characters total. Oversized requirements/feedback are refused,
not silently truncated. Old native IDs, transcripts and cumulative token baselines are
not copied into the successor. Previous sessions and their cost records remain intact.

Both operations require current task/profile versions. Active workers, manual takeover,
archived tickets, unresolved costs, disabled profiles and stale requests are refused.
An audited event records the change without exposing provider credentials or native IDs.

## Verification and remaining work

See [current verification and acceptance](v2-implementation.md#verification-and-acceptance)
for test results. Database tests use a disposable PostgreSQL database, not the application
database. No paid provider requests are needed for those tests.

Remaining code work is explicit: optional paid Thinker/Reviewer execution, removal of
remaining legacy API/read-model/table dependencies, and corresponding UI simplification.
The existing backup scripts target the old named workspace volume; V2 same-path checkout,
native-state and controller-directory backup/restore wiring also remains to be completed.
Do not treat the old `make backup-production` command as a complete V2 recovery backup.
Real Docker/native-SDK smoke tests and the authorized live-task benchmark are also pending;
mocked lifecycle tests are not evidence of production cost or completion rates.
