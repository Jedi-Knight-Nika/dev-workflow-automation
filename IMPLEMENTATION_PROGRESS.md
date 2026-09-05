# Autonomous Engineering Worker — Implementation Progress

This is the durable implementation ledger for the project. Update it whenever a feature is completed, changed, verified, or found blocked. The technical design remains in `autonomous_engineering_worker_mvp_technical_design.md`.

## Status legend

- **DONE** — implemented and verified.
- **IMPLEMENTED** — code exists; full container/integration verification still pending.
- **IN PROGRESS** — partially implemented.
- **NOT STARTED** — no implementation yet.
- **BLOCKED** — implementation or verification is waiting on an external prerequisite.

## 2026-09-04 — Foundation vertical slice

### Project and containers

- **IMPLEMENTED** Docker Compose topology with `frontend`, `backend`, and pgvector-enabled PostgreSQL services.
- **IMPLEMENTED** Dedicated constrained Docker worker service separated from the FastAPI process; it owns scheduling, agent subprocesses, Linear processing, and indexing.
- **IMPLEMENTED** Durable worker registry with startup registration, periodic heartbeats, graceful shutdown status, stale-worker detection API, and live dashboard capacity visibility.
- **IMPLEMENTED** Persistent Docker volumes for PostgreSQL and task workspaces.
- **IMPLEMENTED** Backend and frontend health/dependency ordering.
- **IMPLEMENTED** Environment template and safe Git ignore rules.
- **IMPLEMENTED** Separate production Compose topology with Caddy HTTPS ingress, private application/database ports, persistent certificate state, explicit production environment template, required secret/database URL validation, health ordering, and restart policies.
- **IMPLEMENTED** Production backup job creates atomic timestamped PostgreSQL/workspace backup sets, validates both archives, records SHA-256 integrity metadata, and applies configurable retention.
- **IMPLEMENTED** Explicitly guarded restore job accepts only a named backup set, verifies checksums and archive readability, force-replaces the database and workspace contents, and documents safe stop/restore/restart sequencing.
- **IMPLEMENTED** Make targets for startup, shutdown, logs, migrations, tests, and linting.
- **DONE** Replaced ad-hoc Python `pip` workflow with `uv` for local development and Docker.
- **DONE** Added a committed `uv.lock` dependency lockfile and Python 3.12 pin.
- **DONE** Added a complete environment-variable reference and annotated `.env.example`.
- **IMPLEMENTED** GitHub Actions pull-request and `main` quality workflow.
- **DONE** Added Ruff formatting, MyPy strict static checks, Prettier, and unified `make check`/`make format` commands.
- **DONE** Added application-owned quality commands for backend and frontend.
- **DONE** Added and verified ESLint with TypeScript and Svelte rules; Prettier remains formatting-only.
- **DONE** Standardized frontend development, Docker, and CI on Node.js 22 LTS.
- **DONE** Added Tailwind CSS 4 through the Vite plugin and converted the dashboard from component CSS to Tailwind utilities.
- **DONE** Added service-specific Docker ignore files so local virtual environments and `node_modules` are excluded from build contexts.
- **DONE** Removed unused Git/cURL packages from the control-plane API image; Git will live in the isolated Executor worker image when that phase is implemented.
- **DONE** Removed the redundant frontend runtime `npm install`, switched the build to deterministic `npm ci`, and added an npm BuildKit cache mount for faster rebuilds.
- **DONE** Renamed the workflow to the conventional `.github/workflows/ci.yml` with display name `CI`.
- **DONE** Replaced the public README with a stable, high-level description and moved changing operational details to `DEVELOPMENT.md`.
- **DOCUMENTED** Required GitHub `main` branch ruleset and `Quality gate` status check.

### Backend API

- **IMPLEMENTED** Python 3.12 FastAPI application and versioned `/api/v1` route layout.
- **IMPLEMENTED** Liveness and database-readiness endpoints.
- **IMPLEMENTED** Task create/list/detail endpoints.
- **IMPLEMENTED** Per-task job creation/listing and event timeline endpoints.
- **IMPLEMENTED** Pause and cancel commands.
- **IMPLEMENTED** Durable human takeover/resume: future automation stops, queued work is cancelled, active work may finish without changing task state, and worktree/branch/history are preserved and refreshed on resume.
- **IMPLEMENTED** SSE live-event endpoint with keepalive messages.
- **DONE** Fixed SSE heartbeat cancellation so idle live connections remain open across repeated keepalives; added a regression test.
- **DONE** Replaced process-local SSE authority with PostgreSQL-backed event cursors, ordered replay after connection, event IDs, bounded polling batches, and keepalives so separate API/scheduler containers and restarts cannot lose browser updates.
- **IMPLEMENTED** CORS policy scoped to the local dashboard.
- **IMPLEMENTED** Persisted integration list/configuration API.
- **IMPLEMENTED** Repository create/list/enable API.
- **IMPLEMENTED** Authenticated GitHub repository discovery through the official REST API.
- **IMPLEMENTED** GitHub webhook endpoint with HMAC-SHA256 verification, durable delivery inbox, and duplicate-delivery acknowledgement.
- **DONE** Wired GitHub webhook and worker runtime settings from `.env` into the backend container.
- **IMPLEMENTED** Signed Linear webhook inbox with raw-body HMAC verification, 60-second replay protection, and delivery deduplication.
- **IMPLEMENTED** Asynchronous durable Linear issue processing with explicit configurable trigger label, repository binding, priority normalization, task updates, and archive cancellation.
- **IMPLEMENTED** Per-role agent configuration API with initial role records.

### Durable state

- **IMPLEMENTED** SQLAlchemy async database layer.
- **IMPLEMENTED** Alembic migration bootstrap.
- **IMPLEMENTED** PostgreSQL `vector` extension activation.
- **IMPLEMENTED** Initial `tasks`, `jobs`, and `task_events` tables.
- **IMPLEMENTED** Task/job role and state enums.
- **IMPLEMENTED** Uniqueness constraint for external event deduplication.
- **IMPLEMENTED** Timestamped task event audit trail.
- **IMPLEMENTED** Second migration for integrations, repositories, indexing state, and agent configurations.
- **IMPLEMENTED** Durable webhook-delivery table and uniqueness constraint for provider delivery IDs.
- **IMPLEMENTED** Task pull-request number, URL, and current head SHA persistence.
- **IMPLEMENTED** Revision-aware GitHub check/status/review evidence persistence; old-SHA evidence remains auditable but cannot satisfy current gates.
- **IMPLEMENTED** Durable internal review findings with severity, path/line, reviewer job, workspace fingerprint, and OPEN/RESOLVED/STALE lifecycle.

### Orchestration and workers

- **IMPLEMENTED** PostgreSQL-backed priority job selection.
- **IMPLEMENTED** Concurrent-safe claims using `FOR UPDATE SKIP LOCKED`.
- **IMPLEMENTED** Worker lease tokens and expiration timestamps.
- **IMPLEMENTED** Durable per-task workspace leases acquired by Executor jobs and released on completion.
- **IMPLEMENTED** Executor worktree preparation, latest-plan loading, bounded repository context, structured file writes/deletions, changed-file tracking, and real validation results.
- **IMPLEMENTED** Polyglot Executor runtime includes Python 3.12/uv and Node.js 22/npm; locked Python and npm dependencies are prepared deterministically inside the isolated workspace before checks, using writable ephemeral caches.
- **DONE** Check subprocess timeouts now terminate the full process group and wait for cleanup; failed dependency preparation stops later checks instead of producing misleading cascades.
- **IMPLEMENTED** Executor filesystem boundaries reject absolute/traversal paths and symlink replacement; validation commands are derived from trusted project manifests and never accepted from model output.
- **IMPLEMENTED** Stale worker-result rejection through lease fencing.
- **IMPLEMENTED** Startup recovery of jobs with expired leases.
- **IMPLEMENTED** Local disposable Python subprocess worker lifecycle.
- **IMPLEMENTED** Worker timeout and forced termination handling.
- **IMPLEMENTED** Configurable worker transport: local development uses Python subprocesses, while production launches a fresh Docker container per job through the Engine API and removes it after collecting the result.
- **IMPLEMENTED** Per-job production containers receive only the job ID as command data plus required database/encryption/workspace settings, with read-only rootfs, dropped capabilities, no-new-privileges, bounded tmpfs/PIDs/memory/CPU, and durable-result validation.
- **IMPLEMENTED** Durable bounded job retries: failed/timed-out runs enter database-backed `RETRY_WAIT`, use exponential backoff, survive process restarts, and transition to `NEEDS_HUMAN` only after configured attempt exhaustion.
- **IMPLEMENTED** Pydantic-validated, versioned worker result envelope.
- **IMPLEMENTED** Deterministic role-to-task-state transitions for the foundation flow.
- **IMPLEMENTED** Autonomous Thinker → Executor → Reviewer job chaining with real worktree context.
- **IMPLEMENTED** Dedicated role-specific Context Compiler selects task state, current plan/revision, semantic knowledge, open findings, repository files or diff; deduplicates retrieval and enforces configurable structured context limits.
- **IMPLEMENTED** Bounded local-test, internal-review, GitHub-check, and requested-changes repair routing; exhausted attempts transition to `NEEDS_HUMAN`.
- **IMPLEMENTED** Strict Executor terminal contract distinguishes implementation, test failure, plan mismatch, blocked work, re-planning, and human escalation; non-implementation outcomes cannot smuggle file mutations, and re-planning is bounded by a configurable Thinker-job limit.
- **DONE** Replaced placeholder execution with configured provider dispatch for OpenAI, Anthropic, and Google.
- **IMPLEMENTED** Role-specific Intake/Thinker/Executor/Reviewer system instructions and JSON result parsing.
- **IMPLEMENTED** Strict role-specific structured-output validation with at most two repair attempts, deterministic failure after exhaustion, and provider telemetry persisted for every attempt.
- **IMPLEMENTED** Thinker outcome contract distinguishes validated `PLAN_READY`, `NEEDS_CONTEXT`, and `NEEDS_HUMAN`; missing-context questions and escalation reasons persist in job/event history and drive deterministic task states without automatic execution.
- **IMPLEMENTED** Provider request ID, token counts, model, provider, and duration persistence per worker run.

### Frontend

- **IMPLEMENTED** SvelteKit 5 + TypeScript dashboard container.
- **IMPLEMENTED** Responsive control-center UI.
- **IMPLEMENTED** Task creation form.
- **IMPLEMENTED** Persisted task queue and state summary.
- **IMPLEMENTED** SSE-triggered task refresh.
- **DONE** Production frontend API/SSE connections default to same-origin routing behind Caddy; task detail subscribes to live events and refreshes plan, jobs, PR state, validations, findings, and timeline automatically.
- **IMPLEMENTED** Loading, empty, and API failure states.
- **IMPLEMENTED** Full control-center navigation: Dashboard, Tasks, Repositories, Agents, Integrations, and Settings.
- **IMPLEMENTED** Task inventory and task detail pages with job history and event timeline.
- **IMPLEMENTED** Task detail renders the latest validated Thinker plan as structured goal, targets, ordered steps, tests, constraints, risks, and acceptance criteria instead of leaving plan data hidden in job JSON.
- **IMPLEMENTED** Task detail surfaces Thinker context questions and human-escalation reasons, while the dashboard counts `CONTEXT_PENDING` tasks as needing attention.
- **IMPLEMENTED** Job history exposes each validated agent outcome and summary, so successful transport completion cannot hide semantic outcomes such as re-plan, uncertainty, or human escalation.
- **IMPLEMENTED** Task detail controls for planning, implementation, review, pause, cancel, and workspace preparation.
- **IMPLEMENTED** Manual-control badge plus Take Over Manually and Resume Automation controls.
- **IMPLEMENTED** Task-level Publish/Update PR control with direct link to the resulting GitHub pull request.
- **IMPLEMENTED** Passing internal review automatically commits/pushes the workspace and creates or updates the GitHub PR; failures become durable `AUTOMATIC_PR_PUBLISH_FAILED` human-attention events while the manual Publish/Update control remains available for recovery.
- **IMPLEMENTED** GitHub validation history and guarded Merge control on task detail.
- **IMPLEMENTED** GitHub validation history includes direct evidence links for CI checks, reviews, and inline review comments.
- **IMPLEMENTED** Internal finding history on task detail, including resolution/staleness and exact workspace fingerprint.
- **IMPLEMENTED** Repository selection form and persisted repository inventory.
- **IMPLEMENTED** Repository operational cards expose enabled/disabled controls, clone readiness, remote/indexed SHAs, indexed chunk count, last successful index time, errors, re-indexing, and semantic search.
- **IMPLEMENTED** GitHub repository discovery and one-click selection from the repository page.
- **IMPLEMENTED** Persisted provider/model configuration UI for all four agent roles.
- **IMPLEMENTED** Agent runtime overview with deterministic READY/RUNNING/NEEDS CONFIGURATION/DISABLED status, active-job count, cumulative runs/token usage, and latest provider/model/duration timestamp.
- **IMPLEMENTED** Authenticated OpenAI, Anthropic, and Google model catalog discovery through a unified provider capability API, with per-agent model selectors and manual-ID fallback.
- **IMPLEMENTED** Integration catalog with working-provider versus coming-soon states.
- **IMPLEMENTED** Linear trigger-label and default-repository configuration in the Integrations screen.
- **IMPLEMENTED** Authenticated Linear workflow-state discovery with team-aware state selection and automatic “Ready for Testing” matching.
- **IMPLEMENTED** Configurable Linear “Ready for Testing” workflow state and manual retry control for merged tasks.
- **IMPLEMENTED** Secure credential entry UI; stored credentials are never returned to the browser.
- **IMPLEMENTED** Live integration credential testing for GitHub, Linear, OpenAI, Anthropic, and Google with durable CONNECTED/ERROR status, persisted diagnostics, retry controls, and secret-preserving configuration updates.
- **IMPLEMENTED** Global execution and merge-policy settings overview.

### Verification

- **DONE** Python source compiles successfully with Python 3.14 (the container targets the specified Python 3.12).
- **DONE** Backend Ruff lint passes.
- **DONE** Backend focused test suite passes: 110 tests covering production configuration safety, providers, encryption and atomic credential rotation, GitHub and Linear signatures/events/API calls including configurable lifecycle mapping, GitHub App installation URL/state/callback persistence, inline review comments, authenticated Actions-log enrichment and bounded CI diagnostics, repository indexing/ignore/metadata/incremental-reuse boundaries, PR calls and authoritative restart evidence reconciliation, durable SSE replay/heartbeats, strict Thinker/Executor/Reviewer outcomes, Executor filesystem/dependency and registry-credential boundaries, normalized review fingerprints, retry backoff, hardened Docker worker specifications/log transport, real-workflow evidence validation, and application health.
- **DONE** Svelte type checking passes with zero errors and zero warnings.
- **DONE** SvelteKit adapter-node production build succeeds.
- **DONE** Docker Compose configuration validates successfully.
- **DONE** Backend and frontend Docker images build successfully on Docker Desktop.
- **DONE** The port-conflict fix was verified: all three containers are created without publishing PostgreSQL to the host.
- **DONE** Full Docker Compose stack starts successfully: PostgreSQL initializes, Alembic applies the foundation migration, FastAPI becomes healthy, and SvelteKit listens on its published port.
- **DONE** Three browser regression scenarios pass in Chromium for dashboard execution/health visibility, operator task creation/inventory navigation, and GitHub App configuration/installation launch. Credential-backed task execution remains covered by the separate real-workflow validation harness.
- **DONE** User runtime logs verified PostgreSQL initialization, migration execution, backend readiness, frontend startup, and browser API access.
- **DONE** The user subsequently rebuilt and started the complete Docker stack successfully after clearing Docker Desktop storage; PostgreSQL, migrations, API health, worker dependency, and frontend startup were observed in runtime logs.

## Remaining design phases

- **IMPLEMENTED** AI provider abstraction and OpenAI/Anthropic/Google HTTP adapters; live calls await user credentials for verification.
- **IMPLEMENTED** Encrypted provider credential storage and configuration UI.
- **IMPLEMENTED** GitHub integration: personal-token and GitHub App installation authentication, encrypted structured App credentials, RS256 JWT/token exchange with expiry-aware caching, repository discovery/selection, signed webhook receipt, deduplication, worktrees, deterministic commits, authenticated branch pushes, PR creation/update, validation processing, automated bounded repair routing, and guarded merging.
- **IMPLEMENTED** Repository knowledge indexing: default-branch scanner, bounded text filtering, deterministic language-aware Python/TypeScript/Svelte/Markdown symbol chunks with bounded overlap fallback, content hashes and symbol metadata, OpenAI embeddings, pgvector cosine index/search, durable index status/SHA/error, independent background queue, live repository UI controls, automatic task-context retrieval, unchanged-SHA no-op, changed-file-only reindexing with deletion handling/full-rebuild fallback, and post-merge reindex queueing.
- **IMPLEMENTED** Linear integration: encrypted API-key configuration, signed/deduplicated webhook intake, durable asynchronous issue processing, explicit label trigger, repository binding, priority mapping, updates, cancellation, workflow-state discovery, and post-merge GraphQL state synchronization. OAuth is an optional polished alternative in the design, not an API-key MVP requirement.
- **IMPLEMENTED** Real Thinker provider execution with structured planning instructions, task/repository context, and semantic knowledge retrieval; live quality still depends on the selected model and credentials.
- **IMPLEMENTED** Real Executor: provider-driven code editing, task worktrees, plan loading, manifest-derived checks, structured outcomes, changed-file tracking, bounded iterative repair, deterministic commit/push, and durable leases are implemented.
- **IMPLEMENTED** Internal Reviewer receives the actual Git diff, returns validated structured findings, persists fingerprinted finding history, resolves/stales earlier findings, advances on PASS, and creates bounded Executor repairs on FAIL.
- **IMPLEMENTED** Strict Reviewer outcomes distinguish `PASS`, actionable failure, architectural failure, uncertainty, and human escalation; actionable findings enter the bounded Executor loop, architectural findings enter bounded re-planning, and uncertain/human-required reviews stop automation safely.
- **IMPLEMENTED** Normalized review-finding identity is SHA-256 fingerprinted across workspace revisions with durable occurrence counts; repeated identical findings stop the repair loop at a configurable threshold and escalate with an audit event.
- **IMPLEMENTED** SHA-aware GitHub lifecycle: webhook check/status/review evidence, synchronization invalidation, latest-gate enforcement, head revalidation, automated failure classification, bounded repair jobs, and guarded squash merge are implemented.
- **IMPLEMENTED** Inline GitHub review-comment webhooks become SHA-aware actionable evidence with the full payload available to Executor context; CI and external-review repairs use distinct actions and independently configurable bounded loop limits.
- **IMPLEMENTED** Worker isolation: API and scheduler services are separate and production jobs run in removed-after-use containers with filesystem, capability, PID, memory, CPU, credential, and database restrictions. The documented host firewall/proxy policy is an operator control because Docker Compose cannot enforce provider-domain allowlists alone.
- **IMPLEMENTED** Server deployment code: production Caddy/Compose topology, HTTPS, persistent volumes, secret requirements, health checks, restart recovery, short-lived per-job containers, and verified backup/restore tooling. Actual DNS, host provisioning, firewall rules, and off-host backup transfer are deployment operations rather than missing application code.
## 2026-09-05 — Automatic repository indexing lifecycle

- Repository creation now immediately enters `QUEUED`, so both GitHub discovery selection and manual repository addition trigger initial cloning/indexing without a second click.
- Re-enabling a repository now clears its previous indexing error and queues a synchronization pass; unchanged revisions safely finish without re-embedding, while changed revisions use the existing changed-file incremental path.
- Kept the explicit Index action for operator-requested refreshes and clarified automatic-index behavior in the repositories UI.

## 2026-09-05 — Linear PR lifecycle synchronization

- Added a configurable Linear `In Review` workflow-state mapping alongside the existing `Ready for Testing` mapping, including workflow discovery and conventional-name auto-selection in the UI.
- Successful automatic or manual PR publication now advances the originating Linear issue to `In Review`.
- Linear transition success, skipped configuration, and API failures remain durable task events; a Linear outage does not invalidate an already-published GitHub pull request.

## 2026-09-05 — Intake Agent activation

- Fixed the Intake structured-output contract so its required `EVENT_INTERPRETED` result is accepted and unknown actionability values are rejected.
- Dashboard-created and Linear-imported tasks now enqueue Intake before Thinker instead of bypassing the configured Intake model.
- Persisted Intake interpretation events and passed the normalized interpretation into the Thinker job; Intake requests for human judgment stop safely in `NEEDS_HUMAN`.

## 2026-09-05 — Explicit AI cost accounting

- Added optional per-agent input/output USD rates per million tokens; no provider price is guessed or hard-coded.
- Every provider attempt now persists a nullable estimated USD cost alongside tokens, duration, request ID, provider, model, job, task, and role.
- Agent cards expose cumulative estimated spend and editable rates; migration `0017_worker_run_cost` adds durable storage.

## 2026-09-05 — Conversational GitHub intake

- General PR comments and non-blocking review text are now recognized as untrusted conversational input and queued for the configured Intake Agent.
- Deterministic signals such as approvals, requested changes, and CI conclusions remain on the cheaper software-controlled path.
- Intake-classified informational comments return the task to `WAITING_GITHUB`; actionable interpretations route through Thinker for a revised plan, and uncertain instructions stop for human judgment.
- Duplicate concurrent Intake work for the same task is suppressed while webhook delivery IDs continue providing durable delivery deduplication.

## 2026-09-05 — External GitHub merge/close reconciliation

- Pull requests merged directly on GitHub now complete the durable task, preserve the merge revision, emit an explicit external-merge event, queue repository re-indexing, and synchronize Linear to Ready for Testing.
- Pull requests closed without merge now stop automation in `NEEDS_HUMAN` with an auditable external-close event instead of leaving the task indefinitely waiting for GitHub.

## 2026-09-05 — Durable asynchronous GitHub webhook inbox

- GitHub webhook HTTP handling now performs only signature validation, JSON parsing, durable deduplicated persistence, and immediate acknowledgement; orchestration no longer blocks GitHub delivery requests.
- The scheduler claims persisted GitHub deliveries with row locking and processes them outside the API service, preserving restart recovery and multi-worker safety.
- Delivery attempts, errors, terminal processing time, and five-attempt exhaustion are persisted by migration `0018_webhook_delivery_processing`, preventing a poison event from blocking the scheduler forever.

## 2026-09-05 — Bounded Linear webhook recovery

- Linear deliveries now use the same one-at-a-time, row-locked durable processing lifecycle as GitHub instead of processing a failure-sensitive batch.
- Processing attempts and errors survive scheduler restarts; successful and intentionally ignored deliveries receive terminal timestamps, while poison deliveries stop retrying after five failures.

## 2026-09-05 — Webhook inbox observability

- Added a webhook-health API summarizing pending and failed deliveries plus latest receipt, completion, and error information for GitHub and Linear.
- Integration cards now expose durable inbox backlog/failure health so webhook automation failures are visible without direct database access.

## 2026-09-05 — Credential-backed MVP validation harness

- Added `make validate-real TASK_KEY=...` to observe a real Linear-created task through all four agent roles, persisted PR evidence, and readiness using only the public API.
- Validation fails on timeout, human/context/failure states, missing successful roles, missing PR publication, and optionally a missing repair loop.
- Merge remains explicitly opt-in with `VALIDATE_ARGS="--merge"`; completion validation additionally requires durable confirmation that Linear reached Ready for Testing.

## 2026-09-05 — Operational tooling quality gate

- Backend linting and formatting now cover migrations and root operational Python scripts instead of only application/tests.
- Strict MyPy now checks the real-workflow validator and caught a dead branch during adoption.
- Local `make check` and GitHub CI validate POSIX shell syntax for production backup/restore tools and compile the validation harness.

## 2026-09-05 — Specification-complete operations dashboard

- Added a compact durable activity API for the active job and priority-ordered queued/retry-wait jobs.
- Dashboard now separates current execution, prioritized queue, waiting/ready work, and recent merged tasks instead of relying only on a flat inventory.
- Added GitHub/Linear connection plus webhook-backlog health and repository indexing readiness/failure health to the main operational view.

## 2026-09-05 — External instruction classification and routing

- Linear comment create/update deliveries now associate with existing tasks and enter the durable Intake queue with raw text treated as untrusted context.
- Intake event types are a strict protocol: new task, informational, ordinary review fix, architectural finding, requirement change, or human judgment.
- Informational messages restore the task's prior state, ordinary review fixes enter the bounded Executor repair path, architectural/requirement changes enter bounded Thinker re-planning, and uncertainty stops safely.

## 2026-09-05 — TypeScript browser regression suite

- Added Playwright browser automation entirely in TypeScript with mocked API/SSE boundaries and a real SvelteKit development server.
- Browser coverage verifies current execution, worker/integration/index health, task creation, refreshed task rendering, and navigation to durable task inventory.
- Added a dedicated Node 22 Chromium CI job and made it mandatory for the aggregate `Quality gate`; merge protection can no longer pass when browser behavior is broken.
- Excluded generated Playwright reports/results from Git and Prettier, and verified two Chromium scenarios alongside zero-error Svelte type checking and the production build.

## 2026-09-05 — Bounded CI repair diagnostics

- GitHub check-run, check-suite, and commit-status webhooks now produce a deterministic bounded diagnostic record instead of exposing the complete webhook payload to the coding model.
- Check titles, summaries, relevant text, links, and at most twenty path/line annotations are normalized; diagnostic text is capped at 12,000 characters with explicit truncation.
- The durable webhook inbox still retains the original delivery for audit while Executor repair jobs receive only the focused validation payload.

## 2026-09-05 — Structured application logging

- Added shared JSON logging configuration with UTC timestamps, levels, structured exception data, and context-variable support for API, scheduler, and worker processes.
- FastAPI now emits one secret-safe request event containing only request ID, method, path, status, and duration, and returns the request ID to callers for correlation.
- Query strings, headers, bodies, credentials, prompts, and provider responses are deliberately excluded from request logs.

## 2026-09-05 — Startup workspace and pull-request reconciliation

- Scheduler startup now checks every non-terminal task workspace and reconciles its local Git HEAD when no pull request is authoritative yet.
- Tasks with pull requests are refreshed from GitHub before scheduling resumes; changed remote heads return to `WAITING_GITHUB`, externally closed PRs require human attention, and externally merged PRs are completed durably.
- Reconciled merges queue repository re-indexing and retry the existing Linear Ready for Testing synchronization, while temporary GitHub failures are isolated per task and cannot prevent scheduler startup.

## 2026-09-05 — Configurable Linear lifecycle mapping

- Expanded Linear configuration from only PR/merge targets to Todo, In Progress, In Review, Blocked, Ready for Testing, and Done workflow-state mappings selected from the connected workspace.
- Internal planning/execution/validation states normalize to In Progress, review/GitHub states to In Review, context/human/failure states to Blocked, merge to Ready for Testing, and cancellation to Done.
- Successful synchronization records the internal state durably so repeated scheduler completions do not send duplicate Linear mutations; unavailable configuration or temporary Linear failure remains non-authoritative and cannot roll back task state.
- Integration UI auto-matches conventional workflow names while preserving explicit opt-out for every mapping.

## 2026-09-05 — Disposable-worker credential and egress hardening

- Removed the unused synchronous database URL from per-job containers and explicitly verified that webhook signing secrets are never passed into them.
- Production now requires a separately provisioned `WORKER_DATABASE_URL`, allowing the operator to restrict disposable jobs to their required PostgreSQL tables/actions instead of inheriting the control-plane login.
- Added optional HTTP(S) egress-proxy configuration plus explicit `NO_PROXY` handling for private PostgreSQL traffic; documentation makes clear that host firewall enforcement is required to prevent direct proxy bypass.
- Job containers now explicitly disable privileged mode and add an open-file ceiling alongside the existing read-only root, capability drop, no-new-privileges, PID, memory, CPU, tmpfs, and workspace-mount restrictions.
- Retained the application encryption key because workers must decrypt provider credentials stored by the API; a distinct key without a credential broker or re-encryption mechanism would be nonfunctional security theater.

## 2026-09-05 — Least-privilege worker database provisioning

- Added an idempotent production tool that creates or rotates the disposable-job PostgreSQL login without interpolating raw identifiers/passwords into shell-generated SQL.
- Worker database access defaults to read-only across application tables, with only task/repository updates and worker-run inserts granted for the current job implementation.
- Added a dedicated Make target, production environment parameters, CI shell validation, and a fresh-install/existing-volume deployment sequence that provisions the role after migrations and before Docker job execution.
- GitHub CI now boots pgvector PostgreSQL, applies every Alembic migration, provisions the role twice to prove idempotency, verifies its required read/update/insert grants, and asserts that integration updates and worker-run deletion remain forbidden.

## 2026-09-05 — Encrypted private package registries

- Added working npm and PyPI registry integrations with encrypted backend-only tokens and optional HTTPS registry/index URLs in the integration UI.
- Disposable Executor jobs decrypt configured registry tokens only when preparing locked dependencies and translate them through an explicit environment-variable allowlist.
- Registry credentials are present for `npm ci` and `uv sync` only; project-controlled lint, typecheck, test, and build scripts run without them.
- Dependency output is scrubbed for token/password values before being persisted in job results, preventing accidental credential disclosure through installer errors.

## 2026-09-05 — Strict credential-backed workflow proof

- Real-workflow validation now performs a preflight for connected GitHub/Linear integrations, all four ready agent roles, an enabled fully indexed repository, an online scheduler worker, and failed webhook deliveries.
- Completion requires all four successful roles, PR publication, a durable READY_TO_MERGE decision, current-gate-revision GitHub checks with no pending/failing/blocking evidence, and no unresolved internal findings.
- Post-merge validation correctly checks the PR head recorded by the merge gate rather than the resulting squash-merge commit, then requires confirmed Linear Ready for Testing synchronization.
- Repair-loop proof remains explicitly opt-in with `--require-repair`, and merge remains an explicit `--merge` action.

## 2026-09-05 — Atomic credential-key rotation

- Added a production Compose/Make rotation tool with a non-mutating dry run by default and an explicit confirmation requirement for application.
- Rotation locks credential-bearing integration rows, proves every value decrypts with the old key before producing replacements, and commits all new ciphertext in one transaction so mixed-key partial updates cannot occur.
- Operational documentation requires stopping API/workers, backing up, dry-running, applying, updating the production key, and restarting in a defined recovery-safe order.

## 2026-09-05 — Authenticated GitHub Actions failure logs

- Failed GitHub Actions check runs now trigger authenticated retrieval of the complete check output, annotations, and job log when GitHub exposes the Actions job identifier.
- Plain-text and ZIP job logs are decoded deterministically, filtered to failure/error/assertion/traceback lines, tail-bounded, then passed through the existing 12,000-character repair-context ceiling.
- GitHub diagnostic-fetch failures degrade to webhook-provided evidence without losing or retry-poisoning the original durable delivery.

## 2026-09-05 — Missed GitHub webhook reconciliation

- Scheduler startup now actively fetches current-SHA check runs, commit statuses, PR reviews, and inline review comments for every open tracked pull request.
- Reconciled evidence is revision-filtered, normalized, deduplicated against persisted records, and fed through the same deterministic repair/READY_TO_MERGE evaluator as live webhooks.
- A durable reconciliation event records how many missing evidence records were recovered, closing the restart window where GitHub events could otherwise be missed while the service was offline.

## 2026-09-05 — Interactive GitHub App installation

- Added a backend-generated GitHub App installation URL with an HMAC-signed, random, ten-minute state value and strict App-slug validation.
- Added the public installation callback: it validates state and the numeric installation ID, updates the existing encrypted App credential, exchanges for an installation token, verifies repository access, records CONNECTED/ERROR status, and returns the operator to Integrations.
- The Integrations UI now accepts the GitHub App slug, allows installation ID discovery instead of requiring manual entry, and exposes an Install app action after credentials are saved.
- Added local/production redirect configuration, setup documentation, malformed/tampered/expired state coverage, and installation-URL tests.
- Added browser regression coverage proving the UI persists the expected encrypted-credential input/configuration contract and follows only the backend-generated installation destination.
- Added backend callback coverage proving invalid state is rejected before database access and a valid callback encrypts the installation ID, verifies access, commits CONNECTED status, and redirects to the configured frontend URL.
- Invalid stored App slugs now produce a clear 422 configuration response instead of an internal server error; the UI applies the same slug and numeric App-ID constraints before submission, with endpoint-level coverage for valid and invalid configuration.

## 2026-09-05 — Fail-fast production secret validation

- Production configuration now refuses to start with blank, shorter-than-32-character, known placeholder, or reused application-encryption and GitHub/Linear webhook secrets.
- Local zero-configuration development remains unchanged, while production failures identify the exact invalid variables before the API or worker begins serving.
- Added coverage for valid distinct secrets, each missing/weak/placeholder class, reused secrets, and preservation of development defaults; deployment documentation now states that the example environment cannot be used unchanged.
- Production now also rejects blank/placeholder async or synchronous database URLs and requires the GitHub App browser return destination to be an absolute HTTPS URL, preventing delayed database failures and insecure callback completion after startup.

## 2026-09-05 — Repository indexing exclusion boundaries

- Repository scans now reject generated output, dependency/vendor directories, virtual environments, caches, coverage data, binary/archive/media/font artifacts, minified bundles, and secret-bearing environment/registry configuration paths before reading file contents from Git.
- Filtering is deterministic for both full and changed-file indexing; incremental indexing still deletes any previously stored chunk when a path becomes excluded or is removed.
- Added explicit acceptance coverage for normal Python, Svelte, Markdown, and project metadata plus rejection coverage for traversal, secrets, vendor output, generated output, images, and minified assets.
- Chunk metadata now persists language, symbol, semantic chunk type, exact UTC indexing time, and authority level alongside the existing repository/branch/revision/path/hash columns.
- Incremental indexing loads existing vectors before replacing changed-file rows and reuses them by `(file_path, content_hash)`; only genuinely new chunk content is sent to the embedding provider, and a completely unchanged content set can finish without an embedding API call.
- Reclassified the remaining ledger accurately: Linear's optional OAuth polish, host firewall policy, DNS/host provisioning, and off-host backup transfer are external operations rather than unfinished MVP application code.
