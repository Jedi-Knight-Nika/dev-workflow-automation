# Project architecture, operation, and engineering workflow

This is a source-based report of the current working tree, reviewed on 2026-09-18 against the updated `main` baseline `674951c`, including the subsequent improvement and readability patches. It describes how the software is constructed and runs, not an invented history of who originally built it. Configuration examples describe capabilities, not proof that those capabilities are enabled in a particular deployment.

The repository already contains a comprehensive product reference in `PRODUCT_DESCRIPTION.md`. This report connects that product behavior to the actual modules, processes, data, execution path, and operational constraints, including the improvement passes and higher-risk work intentionally deferred.

## Contents

1. Product and architectural model
2. Technology stack and repository layout
3. Processes and startup
4. Backend layers and module ownership
5. Data and transaction model
6. Complete task-to-commit-to-merge workflow
7. AI, conversations, and spending controls
8. Frontend architecture and live data
9. Activity replay, analytics, and monitoring
10. Security and deployment boundaries
11. Failure handling and operations
12. Production-code simplification
13. Verification and how to extend the system

## 1. What this project is

Autonomous Engineering Worker is a self-hosted engineering control plane. An operator connects repositories and work sources, configures Teams and runtime policies, and authorizes tasks. The system coordinates coding sessions, validates the resulting changes, publishes a GitHub pull request, and conditionally merges it only when the delivery policy permits.

The important distinction is between **decision-making** and **authority**. An AI may interpret a request, propose a plan, edit files, or explain operational facts. It cannot make its own output equivalent to a valid lease, a paid-work reservation, a passing deterministic validation, or a human approval.

There is one fixed engineering lifecycle. This is not a generic user-programmable workflow graph, and the lifecycle visualization is not a separate workflow engine.

The best description of the architecture is a **modular monolith with several process roles and isolated execution containers**:

- Modules share a Python codebase and PostgreSQL schema.
- API serving, execution scheduling, activity projection, and supporting background work have separate runtime entry points or controller loops.
- Paid native turns, validation, and Git transport run in containers with different capabilities.
- The web frontend is a separate SvelteKit application.
- The desktop application wraps the web frontend; it does not implement a second business backend.

This avoids the operational overhead of microservices while retaining module boundaries and separate execution isolation. It is not yet a fully decoupled system: several infrastructure adapters import other modules' infrastructure, and the architecture guard explicitly acknowledges those existing dependencies.

## 2. Technology stack and layout

### Backend

| Technology                             | Role in this repository                                                                                              |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Python 3.12+                           | Application, domain rules, controller processes, and runner implementation.                                          |
| FastAPI and Uvicorn                    | HTTP routing, request validation integration, OpenAPI, and ASGI serving.                                             |
| Pydantic / pydantic-settings           | Request/configuration models, bounds, and environment parsing.                                                       |
| SQLAlchemy 2 async                     | Database adapters, transaction ownership, queries, row/advisory locking.                                             |
| PostgreSQL                             | Durable task state, jobs/leases, receipts, configuration, histories, and projections. Compose targets PostgreSQL 16. |
| asyncpg / psycopg                      | Async application access and synchronous database/migration access respectively.                                     |
| Alembic                                | Ordered schema migrations. The current patch adds revision `0014_task_creation_requests`.                            |
| asyncio / AnyIO / HTTPX                | Bounded background work, cancellation, HTTP integrations, and Docker API transport.                                  |
| cryptography                           | Integration-credential encryption support.                                                                           |
| structlog / prometheus-client / psutil | Structured logging, metrics, and host/resource observations.                                                         |
| tree-sitter grammars                   | Source structure analysis used by repository/context tooling.                                                        |
| Native harness extras                  | Locked Codex and Claude SDK dependencies for runner images; not required as API-process model executors.             |
| uv, Ruff, mypy, pytest                 | Locked dependency installation, lint/format, strict type checks, and tests.                                          |

Declared dependency ranges live in `backend/pyproject.toml`; the reproducible dependency resolution lives in `backend/uv.lock`. Do not treat a range in the manifest as the exact installed version. The Python package version and HTTP app version currently differ (`0.1.0` versus `2.2.0`); neither is a database migration number or an `/api/vN` prefix.

### Frontend and desktop

| Technology                                  | Role                                                                                          |
| ------------------------------------------- | --------------------------------------------------------------------------------------------- |
| TypeScript, Svelte 5, SvelteKit 2           | Typed client logic, reactive UI, filesystem routes, and Node application output.              |
| Vite 6 and adapter-node                     | Development server, production bundling, and Node server adapter.                             |
| Tailwind CSS 4 and component CSS            | Shared styling utilities plus scoped component presentation.                                  |
| ECharts                                     | Operational and analytical charts.                                                            |
| `@xyflow/svelte`                            | Lifecycle/graph presentation. It does not define backend execution authority.                 |
| Canvas, Web Workers, optional Gource viewer | Activity rendering/replay, computation off the main thread, and optional alternate rendering. |
| EventSource and streaming fetch             | Lifecycle/activity notifications and streamed assistant answers.                              |
| Vitest and Playwright                       | Unit tests and browser flows; ESLint, Prettier and svelte-check provide code checks.          |
| Rust / Tauri 2                              | Local desktop launcher and webview shell.                                                     |

`frontend/package.json` requires Node >=22.13; Docker builds use Node 22. JavaScript locks are in `package-lock.json`; Rust uses `desktop/src-tauri/Cargo.lock`. Inspect those locks before changing dependencies rather than relying on a report's version list.

### Top-level map

| Directory/file             | Purpose                                                                                                                       |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `backend/app`              | Python application modules and process entry points.                                                                          |
| `backend/migrations`       | Alembic environment and ordered schema revisions.                                                                             |
| `backend/tests`            | Domain, application, architecture, adapter, HTTP, and database regressions.                                                   |
| `frontend/src/routes`      | Dashboard, tasks, Teams, repositories, integrations, settings.                                                                |
| `frontend/src/lib`         | Typed services, UI components, state/helpers, Observer, and visualization.                                                    |
| `frontend/tests`           | Browser regressions and mocked API flows.                                                                                     |
| `desktop`                  | Tauri project and local loading/error UI.                                                                                     |
| `deploy`                   | Production/execution/monitoring Compose overlays, proxy configuration, images, backup and restore tooling.                    |
| `monitoring`               | Prometheus/exporter/alerting configuration.                                                                                   |
| `scripts`                  | Local startup, real-workflow verification, observability checks, and credential rotation.                                     |
| `docs`                     | Design, operations, rollout, experiment, and review documents.                                                                |
| `compose.yaml`, `Makefile` | Local base stack and common developer commands.                                                                               |
| `.runtime`                 | Local working artifacts; not an authoritative application module. Existing detached worktrees are not folded into this patch. |

## 3. Processes, startup, and deployment modes

### Main process roles

**HTTP API — `backend/app/main.py`:** registers routers, configures logging/CORS, emits request IDs and request metrics, and opens/closes supporting resources through an ASGI lifespan. It can instantiate a scheduler if configured, but base Compose disables that in the API service. The API Docker entry point runs `alembic upgrade head` before Uvicorn.

**Execution controller — `backend/app/scheduler_runner.py`:** starts the scheduler when enabled and runs supporting observability, Observer, and Coordinator controllers. When the scheduler is disabled, it waits rather than repeatedly exiting/restarting. Supporting controllers have their own configuration gates; disabling phase scheduling is not a universal shutdown of every background feature.

**Activity projector — `backend/app/activity_runner.py`:** maintains activity read models independently of the paid execution loop. The execution overlay gives it read-only workspace access for permitted file evidence. Its API/query pool is deliberately small and has short query/lock timeouts.

**Ephemeral runners:** Developer, validator and Git-transport containers are launched for specific operations. They are not normal always-running frontend/API services. The `developer-image` Compose service is an image-building facility, not a permanently active coding agent.

**Frontend:** production builds run through the Node adapter on port 3000. `frontend/src/hooks.server.ts` provides the same-origin `/api` proxy when `API_URL` is supplied. In production, Caddy routes API and UI traffic.

**Desktop:** `desktop/src-tauri/src/lib.rs` resolves the repository root, invokes the shared shell launcher, waits for the UI port, and opens the web console. Startup failure stays visible in the shell. Closing the webview does not stop the Compose stack.

### Local modes

Configure the ignored `.env` from `.env.example` first, including synchronized database URLs, a real application secret, and the required GitHub App mount/configuration. Do not overwrite an existing deployment `.env` with examples.

```sh
sh scripts/start-local.sh --mode console
sh scripts/start-local.sh --mode execution
sh scripts/start-local.sh --mode full
```

| Mode        | Compose selection                                                             | Meaning                                                                           |
| ----------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `console`   | `compose.yaml`                                                                | Base application services; phase scheduler is disabled in the base configuration. |
| `execution` | Base + `deploy/compose.execution.yaml`                                        | Adds native execution infrastructure and related runtime environment.             |
| `full`      | Execution + observability + alerts; macOS monitoring overlay where applicable | Execution-capable stack with monitoring services.                                 |

Selecting execution/full does **not** bypass `SCHEDULER_ENABLED`, harness flags, credentials, Team budgets, repository grants, validation configuration, or automation policy. With those enabled it can resume already authorized queued work. Selecting console is also not a global kill switch for another running controller deployment.

The standalone script defaults to `full` to preserve its previous behavior. Desktop defaults to `console`, and explicitly uses `--no-build`. Normal script startup builds; `--no-build` reuses images and cannot deploy source edits. `AEW_START_MODE` chooses a default, and `AEW_REPO_ROOT` locates a checkout for packaged desktop builds.

For source development, install backend dependencies with `uv sync --locked --all-extras` from `backend` and frontend dependencies with `npm ci` from `frontend`. Run `make dev-backend` and `make dev-frontend` in separate terminals. The frontend Make target points its proxy at localhost:8000. Backend host-run database settings must reference an actually reachable PostgreSQL instance; the base Compose database is private and its container hostname is not a host-machine DSN.

Production uses `deploy/compose.production.yaml` as its base, not the local shell launcher. Add overlays deliberately and follow the production environment/secret/network setup in `PRODUCT_DESCRIPTION.md` and `deploy`. A local console startup is not evidence of a production-secure deployment.

## 4. Backend layering and module ownership

The intended direction is: **HTTP/composition → application use cases and ports → domain rules**, with infrastructure implementing persistence and external capabilities. Python Protocols express ports; the bootstrap layer selects concrete adapters.

- `domain`: state transitions, policy decisions, value objects and other rules that should be testable without HTTP, SQL, Docker, or a provider account.
- `application`: orchestration and contracts for work such as creation, queries, lifecycle changes, and executing a leased phase.
- `infrastructure`: SQLAlchemy records, SQL queries, provider clients, container adapters, and persistence-aware workflows.
- `interfaces/http`: validates/serializes public input and output and translates known failures into HTTP responses.
- `bootstrap`: constructs the actual runtime dependency graph and process/controller resources.

| Module          | Owns                                                                                                                   | Important boundary                                                                                       |
| --------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `engineering`   | Tasks, requirements, dependencies, lifecycle, leased phases, validation and user controls.                             | Canonical work state; an external comment or model response is not automatically a permitted transition. |
| `teams`         | Assignment, native profiles, automation policy, capacity, pause/wake.                                                  | An enrolled native session retains explicit ownership.                                                   |
| `repositories`  | Repository inventory, scope, runtime images and validation commands.                                                   | A connected provider account does not automatically grant every Team every repository.                   |
| `intake`        | Signed delivery ingestion, provider snapshots, reconciliation and interpretation.                                      | Converts external events into canonical evidence/work without trusting them as execution authority.      |
| `agent_runtime` | Harness adapters, prepared sessions, manifests, accounting, context management, bounded editing and runner isolation.  | Model/tool activity is metered and bounded, distinct from deterministic delivery.                        |
| `coordinator`   | Event-driven conversation decisions, clarification and persisted actions/effects.                                      | Modes and explicit authorization constrain its actions.                                                  |
| `supervisor`    | Bounded supervision and execution guidance.                                                                            | Advice/stop decisions do not create merge authority or unlimited paid retries.                           |
| `delivery`      | Git transport, PR publication, review evidence, conditional merge, status synchronization and deployment observations. | GitHub facts and policy are rechecked against the validated revision.                                    |
| `analytics`     | Historical facts, efficiency/cost calculations and forecasts.                                                          | Missing/incomplete usage must not become invented cost savings.                                          |
| `observability` | Infrastructure health, resource attribution, incidents and read-oriented Observer assistance.                          | Operational explanations do not mutate task execution.                                                   |
| `activity`      | Replay projection, file-change evidence, bounded visualization queries.                                                | An eventually updated read model, not the execution source of truth.                                     |
| `platform`      | Settings, sessions, security helpers, integration plumbing, scheduling support and telemetry.                          | Shared mechanisms, not a catch-all for every business rule.                                              |

The repository's architecture tests protect pure layers and record existing cross-module infrastructure relationships. They prevent introducing new private dependency pairs silently; they do not prove complete decoupling or remove historical cycles. This is a practical starting point for adding modules, not a finished textbook Clean Architecture implementation.

## 5. Data, transactions, and durable evidence

PostgreSQL is the durable coordination system; there is no Redis/Celery job broker in this deployment design. SQLAlchemy async sessions are short-lived units of database work, created from configured session factories. The main factory uses connection-pool bounds and pre-ping; supporting subsystems can use separately bounded pools.

| Data family             | Representative records                                                                                                                | Why it exists                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Work                    | `tasks`, `task_dependencies`, `task_repository_scopes`                                                                                | Current status, requirements, scope and prerequisite relationships.          |
| Creation identity       | `task_creation_requests`                                                                                                              | Same-request creation retries resolve to one task.                           |
| Execution history       | `jobs`, `task_events`, `task_phase_runs`                                                                                              | Dispatch, leases, lifecycle evidence and history.                            |
| Native execution        | `developer_sessions`, `ai_runs`, context generations/checkpoints/token policies                                                       | Session identity, usage/cost, continuation and interruption evidence.        |
| Validation/review       | `validation_runs`, `review_cycles`                                                                                                    | Revision-specific proof and subsequent feedback.                             |
| Ownership/configuration | Teams, assignments, profiles, automation, repository runtime profiles, integrations and settings                                      | Who may run what, with which runtime and limits.                             |
| External input/output   | Webhook deliveries, external task snapshots, external status synchronization, task messages                                           | Deduplication, reconciliation and durable conversations/effects.             |
| Coordinator             | Events, runs, actions, human requests                                                                                                 | Decisions and effect execution can be inspected and recovered independently. |
| Read models             | Activity events/file changes/projection state, forecasts, resource summaries, incidents, Observer history and deployment observations | Operator insight without making a browser read the execution authority.      |

`app/platform/persistence/registry.py` imports model modules to register cross-module metadata; model definitions live with their owning adapters. `task_creation_requests` is registered through the task-model module even though the registry need not export each class by name.

Key concurrency mechanisms are lifecycle/requirement versions, job lease tokens/expiry, row locks, advisory locks, unique identities, and guarded state transitions. They solve different problems: a request ID prevents duplicate creation, while a valid job lease authorizes a particular execution attempt. Neither substitutes for the other.

The application is not purely event-sourced. Current state is persisted in task/session/configuration rows alongside histories and projections. Do not assume deleting/rebuilding one projection reconstructs every authoritative database object.

## 6. Complete workflow: task → files → commit → push → PR → merge

### 6.1 Receive and create work

Manual creation starts in `frontend/src/routes/tasks/+page.svelte`, through the typed task service to `POST /api/tasks`. A draft is free by default. The form sends the selected Team, optional start intent, and retry UUID in one request.

`CreateTask` owns the transaction: validate/create domain task, persist it, assign the chosen Team, add the creation event, optionally request execution, remember the retry identity, and commit. Assignment errors roll back the whole operation. Reusing the same UUID with changed details returns 409; identical retries return the existing task without another start request. The browser keeps that identity in memory after failure, not across a full browser restart.

A PostgreSQL transaction advisory lock serializes identical request IDs. Deleting a task cascades away its retry record; this is not a permanent tombstone or cross-tenant idempotency design. An explicitly chosen Team is not replaced by automatic routing. Old API clients can omit `team_id` and `request_id`.

External sources enter through signed webhooks and/or reconciliation, using their own persisted provider delivery/snapshot identities. Linear, Trello, GitHub and Slack do not all have identical workflows or configuration. Integration-specific adapters normalize their evidence before canonical task work occurs. Never treat the manual-creation request ID as universal webhook deduplication.

### 6.2 Enroll a Team-owned execution session

`engineering/infrastructure/job_queue.py:request_execution` calls enrollment within a nested transaction. A configuration problem records an actionable waiting state/event rather than silently launching an incomplete runner.

`enrollment.py` verifies Team/repository availability, enrollment policy and scope, eligible task state, absence of conflicting work, an enabled supported Developer profile, an explicit budget, and safe unused paths. It then persists the native session and enqueues the intake phase.

An enrolled task uses branch `agent/task-<task UUID>`, a task-local repository under `WORKSPACE_ROOT/tasks/<UUID>/repository`, and separate native state/control roots. Existing unregistered directories require inspection rather than automatic overwrite. Provider, harness/model identity, requirement revision and workspace ownership are retained for later checks.

### 6.3 Claim a phase, not an unbounded AI loop

The scheduler has separate dispatch, integration-polling and heartbeat activities. Before new work, it recovers lost leases/receipts. Claiming respects runnable task state, manual takeover, archive flags, dependencies, Team availability, global/Team capacity and retry timing.

Claims use database coordination including row locks with `SKIP LOCKED` and admission/Team-scoped locks. The application wrapper revalidates the lease before execution and watches heartbeats while the phase runs. Revoked or unverifiable authority interrupts the operation rather than permitting spending to continue indefinitely.

Deterministic validation/publication/merge are not all charged against the same Team developer-slot category. Global process concurrency, Developer capacity and validation capacity are separate controls.

### 6.4 Understand status, stage and reason separately

`TaskStatus` answers whether work is runnable, waiting, suspended or terminal: `NEW`, `ACTIVE`, `WAITING_EXTERNAL`, `WAITING_HUMAN`, `PAUSED`, `FAILED`, `CANCELLED`, `MERGED`.

`Stage` answers where it is: `INTAKE`, `PLANNING`, `DEVELOPING`, `VALIDATING`, `PUBLISHING`, `REVIEWING`, `FIXING`, `MERGING`, `COMPLETE`.

`WaitReason` explains why progress stopped, for example configuration, budget, token limit, no progress, provider outage, approval, GitHub review/checks or merge conflict. Preserve these distinctions in new modules and UI; one “running/done” flag loses essential operational information.

The usual path is intake → developing → validating → publishing → reviewing → merging → complete. Planning is conditional. Failed checks or review feedback can return to fixing. Merge recheck returns to review. Pauses retain the stage; requirement revision invalidates stale evidence. Terminal tasks are not implicitly reopened, and manual takeover requires explicit release.

### 6.5 Prepare the repository

The intake executor prepares verified directories and runs the Git transport in its dedicated environment. Preparation refuses to overwrite a nonempty workspace, initializes the task branch, fetches the base branch and checks it out. Credentials/remotes are not persisted in the task's Git config. The resulting base/head SHA is recorded only after checking the task's lifecycle version.

### 6.6 Run the Developer

`SqlPhaseExecutor` dispatches the leased phase. The refactored implementation makes its prerequisites explicit:

- `phase_context.py` loads task/session/profile/Team/repository and effective pricing/token policy and rejects mismatched native profile identity.
- `development_setup.py` checks enabled harnesses, credentials, prices, consumed budget and available reservation, then builds the runner manifest.
- `developer_request.py` assembles the authoritative requirement, current feedback, repair evidence, handoff/checkpoint context and Coordinator delta. Stale revision/SHA handoffs remain blocked.
- `DockerHarness` transports the manifest, mounts, allowed provider environment, progress and supervision callbacks into the native runtime.
- `DevelopTask` orchestrates metered session start/resume, run recording, receipt persistence and checkpoint work.

The controller still decides candidate-validation handoff, bounded repair, continuation acknowledgement, compaction and rollover in the original order. Compaction/continuation are distinct metered operations; they do not share an unlimited reservation. A failed native result is classified by `developer_failures.py`; it is not treated as successful implementation because some files changed.

Codex, Claude, Responses and bounded patch harnesses have different capabilities. In particular, the execution path rejects native-style compaction/rollover requests for Responses/patch rather than pretending they have an equivalent persistent native session.

### 6.7 Deterministic validation and the local commit

`validation_phase.py` selects the repository runtime's validation commands/images, verifies any candidate handoff evidence, and launches the validator. Commands are explicit argv rather than a browser-supplied arbitrary workflow.

`validator_runner.py` is the key answer to **“when does it commit?”**:

1. Require the dedicated non-root container and `/workspace`; reject database, application, AI and GitHub credentials.
2. Verify the expected task branch and fingerprint the candidate files.
3. Run the configured deterministic checks with timeout and bounded output.
4. Reject a nominally passing run if validation itself changed repository files.
5. If checks pass and the worktree is dirty, stage changes and create the local commit using the configured Team author and publication title.
6. Return the exact resulting HEAD SHA, fingerprint, per-command results and bounded change summary.

A native harness may already have created commits; the deterministic validator does not create a redundant commit if the worktree is clean. The important guarantee is that delivery uses recorded successful validation for the **actual current SHA and requirement version**, not the agent's narrative claim.

Validation results persist as per-check evidence. Failures retain bounded feedback and fingerprints for no-progress/repair handling. Optional Reviewer consultation does not replace deterministic checks or GitHub authorization.

### 6.8 Push the validated SHA and publish a PR

`delivery/infrastructure/publication.py` obtains the delivery gate and a short-lived GitHub credential, then runs the publisher against the validated revision.

`git_runner.py` does not push arbitrary dirty work. It requires the expected SHA, copies permitted Git objects into a fresh temporary bare repository, checks the commit/object database, then performs a normal push of that SHA to the task branch. It does not force-push. This separates publication from untrusted repository-local configuration and hooks.

The GitHub adapter creates/reuses/updates PR publication as appropriate and verifies the expected revision. Only after the external operation does the controller persist the PR number/URL under a lifecycle-version check. A stale task during publication produces an inspection/reconciliation failure; external push and database commit are not one atomic distributed transaction.

Therefore these are different milestones: **files changed**, **local commit created**, **branch pushed**, **PR recorded**, **merge confirmed**. The UI/reporting must not collapse them into one “done” event.

### 6.9 Review and guarded merge

Publication transitions into external review waiting. Provider events/reconciliation bring in review messages and checks. Accepted feedback can schedule fixing; policy-authorized progress can schedule merge.

`delivery/infrastructure/workflow.py:merge_phase` rechecks task/job lease identity and expiry, task/Team controls, PR/head, current validation and review evidence, repository allowlist, required checks and approval policy. It conditionally merges the expected SHA, not whatever happens to be the branch head later.

If the same PR head was already merged, recovery observes that result instead of blindly submitting another mutation. If conditions are not yet met, the phase records blockers and returns a merge recheck. Database locks currently span bounded GitHub evidence/merge work in this final gate; shortening that transaction safely requires a separately designed concurrency/recovery change.

Finally, lifecycle/history and external status synchronization record the outcome. Deployment observations are separate evidence about deployment; merged code is not proof of successful production rollout.

## 7. AI roles, conversation, and spending

**Developer:** performs authorized engineering work with explicit runtime/profile/budget settings and persisted native execution evidence.

**Thinker/Reviewer:** optional native consultations. They require supported harness behavior and a configured budget. They do not run as a universal mandatory sequence for every task.

**Coordinator:** processes canonical conversation/events and persists decisions, human clarification and actions. Modes are `off`, `shadow`, `active`; inspect the mode semantics and per-action authority before enabling it. Decisions and effect processing have separate controller loops. It is not another free-running Developer scheduler.

**Supervisor:** optionally assesses bounded evidence and emits guidance or a stop decision. Its allowance must fit alongside Developer work. The controller distinguishes supervisor availability failure from permission to continue spending.

**Observer/Jarvis:** operational assistant built around product facts and saved conversations. Deterministic responses remain available without a local model; optional Ollama explanation is gated by settings, capacity and bounded requests. It is not a paid cloud fallback, does not edit source, and does not gain task-execution authority from the chat UI. Acknowledging/snoozing attention items affects attention state, not code execution.

Price catalog, usage receipts, reservations and calculated costs are separate concepts. Admission rejects incomplete/exhausted accounting rather than assuming unknown usage is free. Context generation/checkpoint and handoff information is versioned so a session cannot silently inherit different requirements or provider/model identity. Provider limits, token limits, no-progress detection and bounded repair are product safety mechanisms, not formatting details to remove during cleanup.

## 8. Frontend architecture and data flow

The route components assemble feature views; `src/lib/services` holds typed API operations and `src/lib/api.ts` centralizes fetch/error behavior. The API helper does not automatically retry mutations. It shows bounded human-readable FastAPI errors instead of raw submitted validation input or proxy HTML and retains the request ID for diagnostics.

| Route                   | Main responsibility                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| `/`                     | Control-center dashboard, throughput, usage, active work and host/operational summaries.       |
| `/tasks`                | Filter/sort, board/list, cursor navigation and atomic task creation.                           |
| `/tasks/[id]`           | Requirements, conversation, controls, session/run/validation/review/resource/history evidence. |
| `/teams`, `/teams/[id]` | Team management, assignment/capacity, profiles, automation and lifecycle presentation.         |
| `/repositories`         | Repository discovery/configuration and runtime/validation readiness.                           |
| `/integrations`         | Provider connection, verification, saved configuration and source destinations.                |
| `/settings`             | Operator preferences, display/locale and monitoring/assistant settings.                        |

Svelte runes (`$state`, `$derived`, `$effect`) express reactive state. Helpers such as `createLatestRequest` and `createLiveRefresh` prevent stale responses or bursts of events from overwriting newer user actions unnecessarily.

`services/task-updates.ts` shares one task-event connection and polling timer among its subscribers. This is not a claim that the entire application has only one connection: the dashboard, activity viewer and assistant transports have specialized lifecycles. On disconnect, visible views reconcile through reads; SSE is not the durable source of task state.

Task-list pagination is keyset-based with a stable UUID tie-breaker. `GET /api/tasks` remains an array and returns `X-Next-Cursor` when another page exists. The board counts/cards describe the currently loaded page, not a newly invented exact database-wide total. This is live navigation, not a repeatable snapshot: mutable sort values can move tasks between pages.

Priority, created, updated and due sorting preserve deterministic tie-breakers and null handling. Invalid cursors or changed-filter reuse return 422. Cursors are navigation hints, not authorization tokens. API failures expose bounded messages and a request ID without echoing submitted validation values or proxy HTML; mutations are not automatically retried.

### Observer readability boundary

- `ObserverShell.svelte`: mounted lifecycle, configuration/status polling, viewport/dock positioning, dialog visibility and notifications.
- `conversation.svelte.ts`: reactive chat state, streaming answers, cancellation/reset and saved conversation loading.
- `ObserverPanelContent.svelte`: history/attention/welcome/message/composer presentation and user-facing attention/preferences actions.
- Existing `api.ts`, `messages.ts`, `position.ts` and `draggable.ts`: transport, reply/source handling, geometry and interactions.

Closing the panel is not resetting a chat. The state stays in its controller, while UI nodes mount/unmount. API activity and paid-work authority remain separate.

## 9. Activity replay, analytics, and monitoring

### Activity replay

The projector translates operational evidence into bounded replay records with sequence numbers, causality and file coverage information. Consumers can be delayed behind execution; the UI explicitly represents delayed, incomplete and sampled history rather than inventing missing file changes.

The viewer preflights a scope/time window, estimates bounds and offers aggregate narrowing when a range is too large. A frozen `through_sequence` supports baseline/history loading. The renderer replays recorded events; its timeline position is not the live canonical task state.

The refactored frontend boundaries are:

- `PreflightForm.svelte`: scope/time/detail selection, capacity feedback and aggregate narrowing.
- `VisualizerShell.svelte`: view lifecycle, renderer ownership, playback and inspector composition.
- `live-stream.ts`: EventSource parsing, monotonic cursor/deduplication, live-history limits and teardown.
- Existing renderer/worker/replay/canvas modules: event reduction and rendering, including fallback behavior.

When hidden, the view pauses and releases its live subscription, then reconnects from the retained cursor. Capacity updates only apply through observed evidence. Reset/out-of-order history requires explicit reconstruction. Closing/disposal releases streams, renderer/worker and resize observers. No replay button grants execution or merge authority.

### Analytics

Analytics reads bounded cohorts of task/run/phase/review facts and derives costs, efficiency and forecasts. The current adapter rejects cohorts beyond its configured code bounds (including 5,000 tasks and 50,000 runs in the main fact read) instead of treating a truncated cohort as a complete report.

The cache coalesces identical requests, permits two different fills concurrently, uses a 20-second TTL, and bounds both entries and in-flight keys at 128. Fills have a 12-second timeout including the capacity wait. A cancelled reader does not cancel another reader's shared fill. This is a process-local optimization, not Redis, a materialized warehouse or an exactly synchronized dashboard snapshot.

### Monitoring

The observability overlay includes Prometheus, cAdvisor, Node Exporter, PostgreSQL Exporter, Blackbox Exporter and optional Alertmanager. Application metrics and persisted incident/resource records supplement exporter observations. Backend-owned queries avoid accepting arbitrary browser PromQL.

Runner attribution distinguishes a task container's resource evidence from host totals. Availability, freshness, missing samples and inference should remain visible. Forecasts and operational explanations are estimates based on evidence, not promises of delivery time.

## 10. Security and isolation

The local base binds public application ports to loopback. The production Caddy configuration terminates ingress, requires operator Basic Auth for the console/API area, leaves provider callbacks to signature verification, and blocks public metrics/alert ingestion. The FastAPI CORS policy is not authentication. This is not a complete multi-tenant identity/RBAC product.

Integration credentials are encrypted and the application key is operationally important. Use the rotation tool and a tested backup/restore procedure; changing a secret string without migrating encrypted records can make credentials unreadable. Do not commit `.env`, private keys, production dumps or native state.

Execution separates capabilities:

- Controller: database access, orchestration and Docker authority. Docker socket access is a major trust boundary.
- Developer: task-scoped workspace/state, allowed provider credentials and restricted egress; no database, GitHub or Docker-socket authority.
- Validator: deterministic tools and workspace, without application/provider/GitHub credentials.
- Publisher: narrowly scoped GitHub credential for validated Git transport; no general paid coding role.
- Observer/activity reads: operational/replay purposes, not permission to start or merge code.

Mounts validate absolute paths, task ownership, separate control/state/workspace roots and symlink constraints. Native containers run as UID/GID 10001 with constrained container configuration. Control manifests must not be writable by the task workspace. Provider network/proxy policy and immutable repository-ready images are deployment requirements, not protections automatically supplied by a Python type annotation.

The execution data root must resolve to the same absolute path on controller and Docker host. A remote Docker host or multi-host runner system requires explicit storage, identity, secret and recovery design; adding worker replicas alone does not provide it.

## 11. Failure handling and operations

| Symptom                               | Inspect first                                                                                         | Do not assume                                           |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Task remains NEW                      | Team enrollment, repository grant/runtime, scheduler flag and worker presence.                        | Creating a task means coding was authorized.            |
| WAITING_HUMAN / missing configuration | Recorded event/reason, enabled profile, credential, verified pricing, budget and validation commands. | Repeated resume clicks can fix missing setup.           |
| Tokens/cost incomplete                | Run receipts, reservation and recovery evidence.                                                      | Missing usage means zero cost.                          |
| Native interruption/no progress       | Failure code, preserved workspace, checkpoint and bounded repair evidence.                            | Starting a fresh paid session is always safe.           |
| Validation failed                     | Exact commands, exit codes, timeout/output tails and candidate revision.                              | The AI's “tests pass” summary is the validation record. |
| Push/PR uncertain                     | Task branch SHA, recorded validation, external PR state and lifecycle version.                        | Database rollback can undo a remote Git operation.      |
| Review/merge waiting                  | Current PR head, checks, eligible approval and Team merge policy.                                     | A passing local check alone authorizes merge.           |
| Stale UI/replay                       | Request ID, stream state, reconciliation polling and projector lag.                                   | A missed browser event means the task did not advance.  |

Operational endpoints include `/health/live`, `/health/ready`, `/metrics` and signed `/webhooks/*`. HTTP request IDs correlate failures with logs. Readiness is not a substitute for validating a real repository runtime.

Use `make operational-check` for shell/Python utility syntax. Backup and restore tools are under `deploy`; real workflow verification is `scripts/validate_real_workflow.py`. Credential rotation, restore, retention and live-provider validation have side effects and require deliberate environment/authorization choices. A successful mock-provider test is not permission to run them against production.

Migration `0014` is additive. Deploy backend and frontend compatibly: an old backend cannot honor the new form's atomic Team-assignment contract. When rolling back application code, the extra table can remain. Dropping it erases retry history and must not race new instances.

## 12. What was simplified in production code

This pass changes actual runtime code, not only test files. It follows responsibility boundaries rather than arbitrarily imposing a maximum file length.

| Before                                                                                                                                     | After                                                                                                                                           | Benefit                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `SqlPhaseExecutor.execute` contained configuration, model pricing, dispatch, prompts, reservations and failure mapping in one long method. | Short top-level dispatch plus named development/continuation methods; typed context/request/admission values and focused setup/failure modules. | A reader can follow phase control without reading every credential, prompt and accounting detail at once. |
| Observer shell owned chat streaming/history as well as status polling, dock, dialog and all content.                                       | Dedicated conversation controller and panel-content component.                                                                                  | Chat lifetime/state, operational polling and presentation have explicit owners.                           |
| Visualizer shell mixed live protocol parsing/bounds with renderer/UI lifecycle and preflight form markup.                                  | Dedicated live-stream module and preflight component.                                                                                           | Transport cleanup/limits can be understood separately from controls and rendering.                        |
| Creation used a “job repository” method that actually authorized execution.                                                                | Explicit `TaskExecution` application port and adapter.                                                                                          | Names describe the side effect rather than hiding it behind CRUD vocabulary.                              |
| Phase action/result mappings were separately maintained in infrastructure.                                                                 | Immutable domain phase registry.                                                                                                                | Fewer duplicated rule tables.                                                                             |

The executor shrank from 723 to approximately 450 lines, Observer shell from 1,331 to approximately 805, and visualizer shell from 1,046 to approximately 850. These counts include imports, markup and CSS; total project lines can increase because named contracts and tests make responsibilities explicit. Line count is not the acceptance criterion.

Preserved behavior includes lifecycle decisions, continuation order, cost guards, prompt content, failure-classification precedence, chat persistence after closing, mobile sizing, cursor monotonicity, live bounds, renderer fallback and disposal. No schema or provider protocol change is introduced by the readability extraction itself.

The follow-up backend pass simplifies code in the existing modules, without new production modules, services or migrations:

- Task and analytics view construction uses named fields instead of long positional argument lists. Persistence loops use descriptive task/run/profile names.
- Run-kind selection and reasoning-effort selection use explicit branches instead of nested conditional expressions. Developer requests and admission values use named fields.
- Bounded repair changes an immutable policy with `dataclasses.replace`, avoiding a serialize/parse round trip while preserving validation.
- Dashboard agent participation is grouped during the existing run traversal, instead of scanning all tasks again for every agent. Repeated runs from one agent still count one task; multiple participating agents may each count that task.
- Phase setup reads pricing once per unique model within that phase, including model routes. A new phase reads fresh pricing; cross-provider routing and missing-price guards remain unchanged.
- Adaptive-patch execution uses readable harness/event names rather than single-letter aliases.

These remove redundant work; no latency or percentage speedup is claimed without production measurements. This does not claim that every remaining file is ideal. Large provider and execution modules still deserve incremental attention as they change. Avoid turning a readability task into an unreviewable rewrite of all delivery/accounting semantics at once.

## 13. Verification, scaling, and extension guide

### What the checks establish

The repository now reuses one JavaScript tooling installation with a root Prettier configuration, ESLint for frontend and desktop JavaScript, Ruff across all owned Python directories, built-in Rust formatting/Clippy, and ShellCheck/shfmt for shell scripts. `make format` only formats; it no longer also applies Python lint fixes. `make check` includes the desktop check. CI has a separate desktop/shell job and checks shared documentation/configuration formatting. Tool versions, prerequisites and individual commands are in the [README](../README.md#code-quality).

This avoids stacking Black/isort/Flake8 alongside Ruff, adding a second web formatter, or introducing another package manager or hook framework. Generated outputs, vendor assets and local runtime data are excluded. Formatting of seven deployment/monitoring YAML files was also checked for parsed-data equality with the original files. The single ESLint 10 finding required removing redundant initial RGB assignments; color conversion behavior is unchanged and existing accent tests pass.

- Backend tests exercise domain/application rules, architecture boundaries, adapters and HTTP contracts; PostgreSQL tests exercise real migrations, locking/concurrent creation, persistence and cursor ordering.
- Refactoring-specific coverage checks request/feedback authority, repair and stale handoff guards, non-development work packets, failure reason precedence and merge dispatch independence.
- Frontend unit tests cover shared helpers/transports; browser tests cover Observer history/chat at desktop/mobile sizes, visualization live/replay/fallback/bounds and existing task/integration races.
- Lint, formatting, Python/TypeScript checking and production builds catch import, type, template and packaging regressions.

These checks do **not** prove live provider credentials, real Docker security on every host, repository-specific toolchains, network access, GitHub approval policy or actual production merge/deployment success. Use authorized sandbox acceptance for those paths.

Validation results for this pass:

| Check                                                                               | Result                                                                                                                       |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Backend suite with PostgreSQL integration                                           | 887 passed, 10 opt-in Docker tests skipped; one dependency deprecation warning.                                              |
| Frontend unit suite                                                                 | 78 passed across 23 files.                                                                                                   |
| Expanded mocked Chromium selection                                                  | 28 passed, 1 failed: Linear destination discovery timing in an unchanged test. Three focused reruns reproduced that failure. |
| Backend Ruff/format/mypy                                                            | Passed.                                                                                                                      |
| Frontend ESLint/Prettier/svelte-check/production build                              | Passed; svelte-check reports zero errors and warnings. Build still emits non-fatal dependency/bundler notices.               |
| Desktop JavaScript, Rust fmt/Clippy, ShellCheck/shfmt and operational script syntax | Passed.                                                                                                                      |
| Full standard `make check`                                                          | Passed using the isolated database. Browser acceptance is separate.                                                          |

The Linear browser failure calls `selectOption` while `#linear-assignee` is still the fallback input, before discovery replaces it with a select. The failure snapshot shows the populated select afterward. The integration component, discovery handler, test, Svelte runtime and Playwright versions were unchanged. This timing-sensitive test remains unresolved rather than being hidden by changing unrelated application behavior or weakening assertions.

`npm audit` reports four low-severity entries through the existing SvelteKit → cookie dependency chain. No moderate, high or critical entries were reported. The suggested forced resolution changes unrelated framework versions; it was not applied during a formatter/linter update. Existing bundler and dependency deprecation notices also remain.

Database verification used a separate disposable PostgreSQL 15 cluster, not the operational database. Deployment/CI targets PostgreSQL 16, so this local result is not a claim to have rerun CI's exact container image. No paid provider task, live push/merge, production restart or deployment was performed. Concurrent dashboard/accessibility edits outside this refactoring were left intact; the final frontend checks include the combined working tree.

Standard commands are `make check`, `make test`, and `make frontend-e2e`; backend database tests require a migrated, isolated `TEST_DATABASE_URL`. Never point the test suite at an operational database. The API container migrates on startup, but host-run tests/servers require their database to be prepared explicitly. CI runs deterministic quality/build/backend checks; the existing decision to keep deployment/browser acceptance separate is unchanged.

### How to add another module cleanly

1. Define its business responsibility and source of truth. Decide whether it owns canonical work, configuration, an external adapter or only a read model.
2. Put pure policy in `domain`, use cases/Protocols in `application`, and SQL/network/filesystem implementations in `infrastructure`.
3. Wire adapters in `bootstrap`; expose typed HTTP schemas/routes rather than leaking ORM rows.
4. Define who owns each transaction. Avoid an adapter that unexpectedly commits halfway through a larger use case.
5. For background work, specify idempotency, lease/cancellation, retry/backoff and recovery before adding another loop. Reuse existing lifecycle/authority when applicable.
6. Add an additive migration and test upgrade/metadata compatibility. Define retention/backfill for read models.
7. Use bounded queries/pagination, explicit timeouts and concurrency limits. Keep paid operations off ordinary reads.
8. Add frontend typed services and small feature components/controllers. Preserve cancellation, stale-response handling, disposal and accessibility.
9. Add contract/regression tests and update this module map, settings documentation and operational signals.

### Scaling priorities

Release acceptance remains pending: follow one authorized sandbox task through ticket → implementation → validation → PR → feedback → merge, including failure recovery. This preserves the deferred end-to-end review previously recorded separately; no live acceptance run is implied by local checks.

Measure task/event counts, dashboard query plans/latency, database pool saturation, queue lag, lease loss, runner slots, CPU/RAM and storage before increasing concurrency. Process-local caches and bounded reads help but are not a long-term analytical warehouse.

Prefer staged improvements: targeted indexes; incremental projections/rollups with freshness semantics; retention with recovery requirements; replacing one cross-module infrastructure dependency with an application contract; and reducing lock-held external I/O only with crash/replay tests. A durable outbox/effect change must preserve stable operation identity and reconcile external success after local failure.

Do not prematurely split every Python module into a microservice. Tenant isolation, remote runner hosts, independent release ownership or demonstrably different scaling demands can justify a service boundary. Those are product/security/operations decisions requiring more than moving functions between files.

### Suggested source-reading order

Start with `engineering/domain/lifecycle.py`, `domain/phases.py`, `application/create_task.py`, `infrastructure/job_queue.py`, `bootstrap/scheduler.py`, `application/jobs.py`, and `infrastructure/executor.py`. Follow the newly named context/request/setup helpers only when studying a Developer turn. Then read `validation_phase.py`, `validator_runner.py`, `delivery/infrastructure/publication.py`, `git_runner.py`, and `workflow.py` for the exact commit/push/merge boundary.

For UI work, read a route, its typed service, `api.ts`, and the relevant controller/component. For operational features, follow bootstrap into analytics, Observer or activity rather than assuming their read models own execution state.
