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
- **DONE** Backend focused test suite passes: 180 tests covering enforced Clean Architecture boundaries/all task and control-plane endpoints/webhook ingestion/SSE event queries/readiness/scheduler delivery/index/startup/presence/job-dispatch ports/merge and every job-completion use case/policy, production configuration safety, providers, encryption and atomic credential rotation, GitHub and Linear signatures/events/API calls including configurable lifecycle mapping, GitHub App installation URL/state/callback persistence, inline review comments, authenticated Actions-log enrichment and bounded CI diagnostics, repository indexing/ignore/metadata/incremental-reuse boundaries, PR calls and authoritative restart evidence reconciliation, durable SSE replay/heartbeats, strict worker outcomes, Executor filesystem/dependency and registry-credential boundaries, normalized review fingerprints, retry backoff, hardened Docker worker specifications/log transport, real-workflow evidence validation, and application health.
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

## 2026-09-05 — Clean Architecture migration: task creation

- Established explicit `domain`, `application`, `infrastructure`, and `bootstrap` packages with documented inward-only dependency rules and manual constructor injection.
- Added a framework-free Task aggregate that owns creation invariants and stable domain state vocabulary without importing FastAPI, Pydantic, SQLAlchemy, HTTP clients, or infrastructure.
- Added application-level task/job/event repository ports, a unit-of-work port, and a `CreateTask` command handler whose transaction commits all task, audit-event, and Intake-job changes or rolls them back together.
- Added concrete SQLAlchemy repository and unit-of-work adapters plus a FastAPI composition dependency; the task-creation route is now a thin transport adapter invoking the use case.
- Added pure use-case commit/rollback tests with in-memory fakes and an automated import-boundary test preventing framework/infrastructure dependencies from entering the domain.
- This is the first behavior-preserving vertical migration. Remaining legacy scheduler, webhook, pull-request, integration, indexing, and worker workflows will move through the same ports incrementally rather than through a high-risk rewrite.

## 2026-09-05 — Clean Architecture migration: guarded merge

- Removed the complete merge gate, head revalidation, GitHub merge, task completion, repository re-index queueing, audit event, and Linear synchronization workflow from the FastAPI route.
- Added a framework-free merge policy with typed validation evidence, latest-evidence reduction, mandatory CI evidence, and explicit blocking statuses.
- Added a `MergeTask` application use case and replaceable merge-workflow port; stale heads are durably recorded before a conflict is returned, successful merges commit before best-effort tracker synchronization, and infrastructure failures roll back and become typed application errors.
- Added the SQLAlchemy/GitHub/Linear adapter and bootstrap wiring; the API endpoint now only invokes the use case and maps typed failures into 404/409/502 responses.
- Added isolated tests for missing CI, blocking reviews, successful merge ordering, stale-head rejection, and missing tasks. The next high-value migration remains the scheduler job-completion state machine.

## 2026-09-05 — Clean Architecture migration: job-completion policies

- Extracted the scheduler's role/outcome decision table into a framework-free domain policy returning typed completion directives for Intake, Thinker, Executor, and Reviewer results.
- Intake informational/fix/re-plan routing, Thinker context/execution decisions, Executor test/re-plan/review routing, Reviewer publish/repair/re-plan/escalation decisions, and repeated-finding cutoffs no longer derive their business meaning from nested scheduler conditionals.
- Extracted retry eligibility and exponential delay into an immutable domain `RetryPolicy`; scheduler persistence now executes that policy instead of owning retry arithmetic and exhaustion rules.
- Added a decision-table test matrix plus repeat-limit, unsupported-role, retry-delay, and retry-exhaustion coverage. Persistence effects remain in the scheduler temporarily and are the next extraction into an application completion handler/port.

## 2026-09-05 — Scheduler dependency inversion

- Removed direct scheduler use of the global SQLAlchemy session factory and worker-launch function; database session creation and worker execution are explicit constructor dependencies.
- Added an application-layer `WorkerRunner` port and transport-neutral execution result, with a configured infrastructure adapter selecting local subprocess or isolated Docker transport from settings.
- Added a dedicated scheduler composition root used consistently by the FastAPI lifespan and standalone worker service, keeping infrastructure construction out of runtime orchestration.
- The scheduler still operates legacy SQLAlchemy sessions internally, but it can now be tested with injected sessions/worker results and can migrate completion persistence to a unit-of-work adapter without changing process entrypoints.

## 2026-09-05 — Clean Architecture migration: failed job completion

- Added a `CompleteFailedJob` application use case with a dedicated unit-of-work port and command/context DTOs independent of SQLAlchemy and transport implementations.
- Failed and timed-out completion now lease-fences the worker result, records terminal diagnostics, releases workspace ownership, applies the domain retry policy, persists retry timing/audit events or escalates the task, commits atomically, and synchronizes Linear behind an infrastructure adapter.
- Jobs finishing during manual takeover preserve operator control and emit the existing takeover audit event instead of entering retry or escalation paths.
- Scheduler `_finish` now delegates non-successful completion immediately; it no longer contains failure retry arithmetic, mutation, exhaustion, or tracker-sync logic.
- Added isolated use-case coverage for retry scheduling, exhaustion, manual takeover, and stale worker results. Successful role completion remains the next application-handler extraction.

## 2026-09-05 — Clean Architecture migration: Intake completion

- Added a `CompleteIntakeJob` application handler and Intake-specific completion unit-of-work port; successful Intake jobs now leave the scheduler before it opens a legacy completion transaction.
- The SQLAlchemy adapter lease-fences and records the result, releases workspace ownership, applies typed domain directives, restores informational-comment state, queues bounded external-feedback repair or re-planning, queues initial planning, persists audit events, commits, and synchronizes Linear.
- Manual takeover and stale-result behavior remain preserved, while repair/re-plan job ceilings stay configuration-driven at the infrastructure boundary.
- Removed every Intake outcome/state/event branch from `Scheduler._finish()` and added isolated handler tests for domain-directive application and manual-takeover preservation. Thinker completion is the next role migration.

## 2026-09-05 — Clean Architecture migration: Thinker completion

- Added a `CompleteThinkerJob` application handler and a Thinker-specific unit-of-work port that contain no SQLAlchemy, FastAPI, or transport dependencies.
- Successful Thinker completion now exits the scheduler through an explicit command, uses the framework-free completion policy, and delegates lease fencing, result persistence, workspace release, task transitions, Executor enqueueing, audit events, atomic commit, and Linear synchronization to the SQLAlchemy adapter.
- Preserved stale-result rejection and manual-takeover behavior while removing every Thinker outcome/state/event branch from the legacy scheduler transaction.
- Added isolated handler coverage for plan-ready execution and manual-takeover preservation. Executor completion is the next role migration.

## 2026-09-05 — Clean Architecture migration: Executor completion

- Added a framework-independent `CompleteExecutorJob` application handler and an Executor completion port with explicit command and transaction-context DTOs.
- Moved successful Executor result persistence, lease fencing/release, local-validation transition, Reviewer enqueueing, bounded repair, bounded re-planning, escalation events, atomic commit, and Linear synchronization into the SQLAlchemy infrastructure adapter.
- Scheduler completion now dispatches successful Executor results and returns without executing Executor business or persistence branches; stale leases and manual takeover retain their existing safeguards.
- Added isolated handler tests for implemented-result routing and takeover preservation. Reviewer completion remains the final successful-role branch in the legacy scheduler transaction.

## 2026-09-05 — Clean Architecture migration: Reviewer completion

- Added a `CompleteReviewerJob` application handler and Reviewer-specific unit-of-work port covering typed outcome selection, repeated-finding escalation, and post-commit publication orchestration.
- Moved review-result persistence, repair/replan ceilings, task transitions, audit events, tracker synchronization, PR publication, and recoverable publication-failure escalation into the SQLAlchemy infrastructure adapter.
- Removed the final successful-role transaction and its publication/repair/replan helper methods from `Scheduler`; completion now dispatches all four worker roles through application handlers and rejects unsupported successful results explicitly.
- Added isolated coverage for publication routing, repeated-finding limits, and manual takeover. The scheduler completion state machine migration is now complete; task lifecycle routes are the next backend boundary.

## 2026-09-05 — Clean Architecture migration: task lifecycle controls

- Added a framework-free task lifecycle policy defining pause, cancellation, takeover, and resume transitions, including terminal-task and manual-control invariants.
- Added a `ChangeTaskLifecycle` application use case and persistence port; FastAPI routes now translate HTTP input/errors only and return domain task snapshots rather than mutating ORM records.
- Added a SQLAlchemy lifecycle unit of work that locks the task, cancels queued work atomically where required, refreshes Git revision/fingerprint on resume, records the correct user audit event, and commits the transition.
- Added isolated policy/use-case coverage for all four controls, queued-job directives, PR-aware resume state, workspace refresh, missing tasks, and rejected terminal takeover. Workspace creation, manual job enqueueing, PR publication, Linear retry, and task queries remain in the task API migration backlog.

## 2026-09-05 — Clean Architecture migration: workspace preparation

- Added a `PrepareTaskWorkspace` application use case and replaceable workspace workflow port with typed not-found, conflict, and unavailable failures.
- Moved task/repository locking and validation, Git workspace preparation, ready-event persistence, commit/rollback behavior, and ORM-to-domain mapping into a SQLAlchemy/Git infrastructure adapter.
- Reduced the workspace FastAPI endpoint to use-case invocation and HTTP error/result translation; it no longer performs database mutations or Git orchestration.
- Centralized ORM-to-domain Task mapping for reuse by lifecycle and workspace adapters and added isolated application-port delegation coverage. Manual job enqueueing and PR publication are the next task command boundaries.

## 2026-09-05 — Clean Architecture migration: manual job enqueueing

- Added an `EnqueueTaskJob` application handler, typed enqueue command/result DTOs, and a replaceable job-enqueue workflow port independent of FastAPI and SQLAlchemy.
- Moved task locking, paused/cancelled guards, role conversion, durable job/event creation, commit, refresh, and ORM-result mapping into the SQLAlchemy adapter.
- Reduced the manual-job endpoint to request translation, use-case invocation, typed 404/409 mapping, and response serialization.
- Added isolated application-port delegation coverage. Manual PR publication, Linear retry, and read/query endpoints remain in the task API migration backlog.

## 2026-09-05 — Clean Architecture migration: PR publication and tracker retry

- Added separate application handlers and replaceable ports for manually publishing a task pull request and retrying merged-task tracker synchronization.
- PR publication now performs task/repository locking and validation, Git/GitHub publication, rollback, typed error conversion, and transport-neutral result mapping inside the infrastructure adapter.
- Tracker retry now performs task lookup, merged-state enforcement, and Linear synchronization behind its infrastructure adapter; both FastAPI routes only translate requests, typed failures, and responses.
- Added isolated delegation tests for both use cases. The remaining task API work is read/query extraction plus removal of the workspace-refresh infrastructure exception leak.

## 2026-09-05 — Clean Architecture migration: task queries and resume error boundary

- Added `ListTasks` and `GetTask` application query handlers with a replaceable read port returning domain Task snapshots instead of ORM entities.
- Added the SQLAlchemy query adapter with centralized ORM-to-domain mapping; the list/get FastAPI routes now perform only query invocation, typed not-found translation, and response serialization.
- Replaced the task API's direct Git exception dependency with an application-level workspace-refresh failure emitted by the lifecycle infrastructure adapter.
- Added isolated list limit, retrieval, and missing-task coverage. Job/event/validation/finding history queries are the remaining endpoints in `api/tasks.py` that access SQLAlchemy directly.

## 2026-09-05 — Clean Architecture migration: task history queries

- Added transport-neutral job, event, validation, and review-finding view DTOs plus a single application query port and `QueryTaskHistory` handler.
- Added a SQLAlchemy read adapter preserving the existing ordering for jobs/events and reverse-chronological validations/findings, with centralized job mapping reused by manual enqueueing.
- Migrated all four history endpoints to the application read boundary; `api/tasks.py` now has no direct SQLAlchemy session, ORM model, or legacy service imports.
- Added isolated coverage proving all history operations delegate through the query port. The task API boundary migration is complete; the control-plane API is the next large transport boundary.

## 2026-09-05 — Clean Architecture migration: operations dashboard reads

- Added transport-neutral activity and webhook-health views, an `OperationsQueries` port, and a `QueryOperations` application handler.
- Moved active/queued job selection, deterministic ordering/limits, provider delivery counts, latest timestamps, and latest-error lookup into a SQLAlchemy query adapter.
- Reduced the activity and webhook-health endpoints to application-query invocation and response serialization while preserving their existing API contracts.
- Added isolated application delegation coverage. Provider catalog, workers/agents, integrations, repositories, and knowledge search remain in the control-plane migration backlog.

## 2026-09-05 — Clean Architecture migration: provider catalog

- Added transport-neutral provider/model catalog views, typed configuration/support failures, a provider-catalog workflow port, and a `DiscoverProviderCatalog` application handler.
- Moved integration credential lookup, backend-only decryption, provider construction, capability discovery, and remote model listing into an infrastructure adapter.
- Reduced the provider catalog endpoint to application invocation, typed 404/409 mapping, and response serialization without exposing decrypted credentials across the boundary.
- Added isolated delegation coverage. Worker/agent reads, GitHub/Linear discovery, integration management, repositories, and knowledge search remain in the control-plane backlog.

## 2026-09-05 — Clean Architecture migration: worker visibility

- Added transport-neutral worker snapshots/views, a worker query port, and a `QueryWorkers` application handler.
- Extracted the three-heartbeat online/freshness rule into a deterministic framework-free domain policy with an injectable evaluation time.
- Moved worker ordering and ORM mapping into the SQLAlchemy read adapter; the endpoint now combines the query handler with configured heartbeat timing and serializes the result.
- Added coverage for recent, stale, and explicitly stopped workers. Agent reads and updates are the next control-plane boundary.

## 2026-09-05 — Clean Architecture migration: agent configuration

- Added transport-neutral agent configuration commands/views, an application management handler, and a replaceable persistence workflow for reads and updates.
- Moved default role creation, configuration persistence, active-job counts, cumulative token/cost totals, latest-run metadata, ordering, and ORM mapping into the SQLAlchemy adapter.
- Extracted disabled/unconfigured/running/ready classification into a framework-free domain policy and made both list and update endpoints return the same complete operational view.
- Added application delegation and status decision-table coverage. GitHub/Linear discovery, integration management, repositories, and knowledge search remain in the control-plane backlog.

## 2026-09-05 — Clean Architecture migration: external integration discovery

- Added transport-neutral repository and workflow-state views, a shared integration-discovery port, and a `DiscoverIntegrations` application handler.
- Moved encrypted credential lookup/decryption, GitHub App/token auth resolution, GitHub client construction, Linear client construction, remote calls, and result mapping into infrastructure.
- Migrated GitHub repository and Linear workflow-state discovery endpoints to typed application invocation and consistent missing-configuration handling.
- Added isolated coverage for both discovery paths. GitHub App installation flow, integration management, repositories, and knowledge search remain in the control-plane backlog.

## 2026-09-05 — Clean Architecture migration: GitHub App installation

- Added a GitHub installation application handler, workflow port, typed invalid-state/not-configured/invalid-slug failures, and a transport-neutral callback result.
- Moved signed-state creation and verification, integration lookup, credential decryption/re-encryption, installation ID persistence, GitHub App auth resolution, connectivity validation, status/error persistence, and redirect selection into infrastructure.
- Reduced install URL and callback routes to application invocation plus typed HTTP/redirect translation; invalid callback state is still rejected before any database access.
- Reworked callback coverage around both route delegation and the concrete encrypted adapter. Integration configuration management is the next control-plane boundary.

## 2026-09-05 — Clean Architecture migration: integration management

- Added typed integration commands/views, an application management handler, and an encrypted infrastructure workflow for listing, configuration, and connectivity verification.
- Moved credential encryption/decryption, provider-specific GitHub/Linear/AI/registry validation, status/error persistence, and ORM mapping out of FastAPI.
- Migrated all integration CRUD/test endpoints to the application boundary with typed missing-credential handling while preserving encrypted credential storage.
- Ruff, MyPy, and the full 160-test backend suite pass. Repository management is the next control-plane boundary.

## 2026-09-05 — Clean Architecture migration: repository management

- Added typed repository commands/views, an application management handler, and a SQLAlchemy workflow for list/create/enable/disable/index-queue operations.
- Moved row locking, missing/disabled validation, index state transitions, commits, clone-status derivation, and knowledge-chunk counting out of FastAPI.
- Migrated repository management endpoints to typed application invocation and 404/409 translation while preserving response enrichment and ordering.
- Ruff, MyPy, and the full 160-test backend suite pass. Semantic search and deeper indexing orchestration remain next.

## 2026-09-05 — Clean Architecture migration: semantic knowledge search

- Added typed knowledge results, repository missing/not-ready failures, a search application handler, and a replaceable search workflow port.
- Moved repository readiness lookup, vector-search invocation, and result normalization into infrastructure; limit clamping is enforced at the application boundary.
- Migrated the search endpoint to typed use-case invocation and 404/409 translation. This removed the final direct SQLAlchemy session, ORM model, and legacy service import from `control_plane.py`.
- Added limit/delegation coverage; Ruff, MyPy, and all 161 backend tests pass. Webhook and indexing service orchestration are the next major boundaries.

## 2026-09-05 — Clean Architecture migration: webhook ingestion

- Added a webhook ingestion application handler, replaceable port, and typed missing-header/invalid-payload/invalid-signature failures.
- Moved GitHub/Linear signature validation, timestamp freshness validation, JSON decoding, repository metadata extraction, durable delivery creation, commit/rollback, and duplicate-delivery handling into infrastructure.
- Rebuilt the webhook routes as thin body/header adapters preserving GitHub 202/duplicate 200 and Linear idempotent 200 behavior.
- Ruff, MyPy, and all 161 backend tests pass. Durable GitHub/Linear delivery interpretation remains the next webhook boundary.

## 2026-09-05 — Scheduler delivery and indexing inversion

- Added application ports/handlers for durable GitHub/Linear delivery processing and queued repository-index processing.
- Added session-owning infrastructure adapters around the existing provider processors so transaction construction no longer leaks into scheduler orchestration.
- Removed direct GitHub event, Linear event, and indexing service imports/calls from `Scheduler`; these capabilities are now explicit constructor dependencies wired in the composition root.
- Added delegation coverage for both handlers; Ruff, MyPy, and all 163 backend tests pass. The internal legacy processors themselves remain the next deeper migration boundary.

## 2026-09-05 — Scheduler startup and worker-presence inversion

- Added application ports/handlers for startup maintenance and worker presence, backed by session-owning SQLAlchemy infrastructure adapters.
- Removed direct expired-job recovery, restart reconciliation, worker registration, heartbeat mutation, and shutdown persistence from the scheduler.
- The composition root now constructs explicit startup and presence dependencies using a stable process worker ID; the scheduler only controls timing and lifecycle.
- Added startup delegation coverage; Ruff, MyPy, and all 164 backend tests pass. Job claiming/execution preparation remains the scheduler's last direct persistence-heavy path.

## 2026-09-05 — Scheduler job-dispatch inversion

- Added a typed claimed-job value object, job-dispatch port, and application handler for claiming and preparing leased work.
- Moved database session ownership, atomic job claiming, lease-token validation, Executor workspace lease acquisition, contention requeueing, and the transition to running into a SQLAlchemy infrastructure adapter.
- Removed the scheduler's final direct SQLAlchemy session, ORM Job entity, and orchestration-service dependencies; its worker identity is now supplied by the composition root.
- Added isolated application delegation coverage; Ruff, MyPy, and all 165 backend tests pass. Deeper GitHub/Linear delivery and indexing implementations remain behind adapters and are the next migration targets.

## 2026-09-05 — Durable event-query inversion

- Added transport-neutral event views, a bounded event-query application handler, and a replaceable read port for latest-cursor and replay-page queries.
- Moved SQLAlchemy session creation, aggregate cursor lookup, durable event ordering, replay limits, and ORM mapping into a persistence adapter.
- Removed direct database and ORM dependencies from the SSE API module while preserving reconnect replay, invalid-cursor recovery, and heartbeat behavior.
- Added isolated delegation and limit coverage; Ruff, MyPy, and all 166 backend tests pass. The health endpoint and internal delivery/index processors remain persistence-heavy migration targets.

## 2026-09-05 — Readiness probe inversion

- Added an application readiness use case, replaceable probe port, and typed service-unavailable failure that hides infrastructure exception details.
- Moved the concrete database connectivity query into a SQLAlchemy persistence adapter supplied through FastAPI dependency wiring.
- Removed SQLAlchemy and database-session imports from the health API; liveness remains deliberately independent from database readiness.
- Added success and failure-path unit coverage; Ruff, MyPy, and all 168 backend tests pass. Internal GitHub/Linear delivery and indexing processors remain the largest persistence-heavy targets.

## 2026-09-05 — Linear webhook domain-policy extraction

- Extracted Linear priority normalization, label normalization, configured-repository parsing, and external-comment interpretation into the framework-free domain layer.
- Kept the delivery processor focused on transactional coordination while moving deterministic payload decisions out of the SQLAlchemy service module.
- Redirected policy tests to the domain boundary so these rules are validated without importing persistence infrastructure.
- Ruff, MyPy, and all 168 backend tests pass. Linear delivery transaction coordination and GitHub/index processing still require deeper port-based decomposition.

## 2026-09-05 — Agent-role boundary cleanup

- Added a framework-free `AgentRole` domain enum for the four supported worker responsibilities.
- Replaced the control-plane route's direct ORM `JobRole` dependency with the domain role type while preserving FastAPI path validation and response values.
- Updated the agent response contract to use the domain enum, removing the final direct database-model import from `api/control_plane.py`.
- Ruff, MyPy, and all 168 backend tests pass; `api/events.py`, `api/health.py`, `api/tasks.py`, `api/webhooks.py`, and `api/control_plane.py` now avoid direct persistence imports.

## 2026-09-05 — Scheduler domain types and application boundary enforcement

- Added transport-neutral domain execution states and reused the domain agent-role enum for worker-result dispatch.
- Removed the scheduler's final ORM-model import; scheduler orchestration now depends only on settings, schemas, application handlers/ports, and domain values.
- Added an AST architecture test that rejects FastAPI, Pydantic, HTTP clients, SQLAlchemy, database, infrastructure, integration, bootstrap, API, or legacy-service imports anywhere in the application layer.
- Ruff, MyPy, `git diff --check`, and all 170 backend tests pass. The clean dependency direction is now mechanically guarded for both domain and application layers.

## 2026-09-05 — Shared webhook delivery retry policy

- Added a validated domain policy for delivery exhaustion thresholds and bounded persisted failure messages.
- Wired both GitHub and Linear delivery processors to the same policy, eliminating duplicated retry decisions and preventing provider-specific semantic drift.
- Added boundary, truncation, and invalid-configuration coverage; Ruff, MyPy, and all 174 backend tests pass.

## 2026-09-05 — Repository indexing path policy extraction

- Moved generated-directory, binary/archive/font/media, secret-file, traversal, absolute-path, and minified-bundle exclusion rules into the framework-free indexing domain.
- Kept repository scanning responsible for Git object access and content-size/binary checks while delegating deterministic path eligibility to the domain policy.
- Redirected indexing policy tests to the domain boundary; Ruff, MyPy, and all 174 backend tests pass.

## 2026-09-05 — Repository indexing content policy extraction

- Added domain-owned changed-path normalization and configurable embedding-vector dimension validation instead of coupling those deterministic rules to SQL persistence code.
- Added a domain `SourceChunk` value object and incremental embedding-reuse selection based on stable file-path/content-hash identity.
- Updated indexing orchestration and tests to consume the domain contracts while retaining Git, provider, and database operations in the outer layer.
- Added explicit configurable-dimension and invalid-configuration tests; Ruff, MyPy, `git diff --check`, and all 176 backend tests pass.

## 2026-09-05 — Repository text-chunking domain extraction

- Moved deterministic content hashing, newline-aware chunk windows, overlap behavior, and source-chunk construction into the framework-free indexing domain.
- Moved language detection and module/section/symbol/text metadata classification into the same domain boundary.
- Updated indexing orchestration and policy tests to consume the domain functions while syntax-boundary discovery, Git access, embeddings, and persistence remain outer-layer concerns.
- Ruff, MyPy, and all 176 backend tests pass; the architecture guard confirms the extracted code has no framework, persistence, provider, or service dependencies.

## 2026-09-05 — Structured source and content-safety domain extraction

- Moved top-level Python AST boundaries, TypeScript/JavaScript declaration boundaries, Svelte script boundaries, Markdown headings, and structured source-to-chunk assembly into the indexing domain.
- Removed AST and regular-expression parsing responsibilities from the legacy indexing service, leaving it to coordinate repository access and downstream persistence.
- Added a configurable domain content-safety rule that rejects NUL-containing binary data, oversized UTF-8 content, and invalid size limits before chunking.
- Ruff, MyPy, `git diff --check`, and all 178 backend tests pass. The complete deterministic indexing pipeline is now domain-owned; Git, embeddings, and SQL remain outer-layer integrations.

## 2026-09-05 — Legacy integration-service namespace cleanup

- Moved repository indexing/search, GitHub delivery processing, Linear delivery processing, and startup reconciliation implementations from the ambiguous legacy `services` namespace into infrastructure.
- Updated scheduler adapters, semantic-search adapters, context compilation, startup maintenance, reconciliation, and webhook-policy tests to reference their explicit outer-layer implementations.
- Preserved the existing application ports and handlers, so orchestration continues depending inward while SQLAlchemy, Git, provider HTTP, encryption, and remote API details remain outside.
- Ruff, MyPy, `git diff --check`, and all 178 backend tests pass. Remaining legacy services are worker/executor helpers and reusable persistence/integration primitives still consumed by infrastructure adapters.

## 2026-09-05 — Worker runtime and persistence primitive relocation

- Moved Docker/local subprocess transport, Executor filesystem/check execution, Context Compiler, and structured-output validation/repair under `infrastructure/workers`.
- Moved job claiming, enqueueing, durable event recording, expired-lease recovery, workspace lease acquisition/release, and retry promotion into `infrastructure/persistence/job_operations.py`.
- Moved the scheduler runtime under infrastructure after its database decisions had already been inverted behind application ports; bootstrap remains the sole composition root.
- Updated every worker, adapter, persistence workflow, test, and integration caller; Ruff, MyPy, `git diff --check`, and all 178 backend tests pass.

## 2026-09-05 — Legacy service layer removal

- Moved encryption and credential rotation into infrastructure security, including the production Compose entrypoint and compatibility script.
- Moved Linear synchronization, GitHub PR operations, review persistence, and Git workspace mechanics into explicit infrastructure modules.
- Removed every Python module from the ambiguous `app/services` namespace and added an architecture test that fails CI if miscellaneous service modules are reintroduced.
- Updated all application entrypoints, workers, adapters, infrastructure workflows, deployment configuration, and tests to use the explicit packages.
- Fixed the remaining Svelte `ShowMore` state-capture warning; the canonical frontend check now passes ESLint, Prettier, 0-error/0-warning Svelte type checking, 21 unit tests, and the production build.
- Ruff, MyPy, `git diff --check`, and all 179 backend tests pass.

## 2026-09-05 — Domain-owned operational states

- Moved task, job, integration, and repository-index lifecycle enums out of SQLAlchemy models and into framework-free domain modules.
- ORM mappings now consume and explicitly re-export those domain enums for backward compatibility, preserving existing PostgreSQL enum names and stored values.
- Transport schemas now depend on domain states instead of persistence models, removing their final database-layer dependency.
- Added a CI architecture guard forbidding persistence imports from transport schemas.
- Ruff lint/format, strict MyPy, `git diff --check`, all 180 backend tests, the full frontend check with 0 Svelte warnings and 21 unit tests, and both development/production Compose configuration validation pass.

## 2026-09-05 — Post-migration container verification

- Added the standard SvelteKit `prepare` lifecycle and copied `svelte.config.js` before Docker dependency installation so clean container builds generate framework types without the missing-tsconfig warning.
- Rebuilt the Python 3.12 backend, Node 22 Svelte frontend, and polyglot Python/Node/Git worker images successfully after all module relocations.
- Started the complete Compose stack from the rebuilt images; PostgreSQL and FastAPI report healthy, the dedicated scheduler worker remains running, and the frontend remains running.
- Verified `GET /health/ready` returns database-ready JSON and the frontend root returns HTTP 200 through the published host ports.

## 2026-09-05 — Guided GitHub repository onboarding

- Reworked repository setup into an explicit three-step flow: connect/authenticate GitHub, select the repositories the AI may access, then observe automatic knowledge preparation.
- Added connection-aware controls and navigation between GitHub authentication and repository selection; discovery remains unavailable until the integration has been verified as connected.
- Replaced internal index-state presentation with user-facing AI knowledge states: not ready, embedding, AI ready, and failed, including chunk counts and actionable retry controls.
- Kept clone-URL import available as a secondary fallback while making authenticated GitHub discovery the primary path.
- Added end-to-end repository removal through the application port, SQLAlchemy adapter, HTTP API, and typed frontend service. Removal also deletes repository knowledge through the existing database cascade and requires explicit browser confirmation.
- The frontend passes ESLint, Prettier, TypeScript/Svelte checks with 0 errors and 0 warnings, all 21 unit tests, and its production build. Ruff and strict MyPy pass and all 181 backend tests pass.

## 2026-09-05 — Vercel-style GitHub App connection

- Removed GitHub App IDs, slugs, installation IDs, private keys, and personal tokens from the end-user interface.
- Moved the platform-owned GitHub App configuration to server environment variables; it is configured once by the deployment operator and never exposed by the API.
- The GitHub card now offers one Connect GitHub action. It redirects to GitHub's installation approval, validates a signed/expiring callback state, records the returned installation ID encrypted, verifies repository access with GitHub, and returns the user to repository selection.
- Added Compose and environment-template parameters for the GitHub App slug, ID, private key, and post-install return page.
- Ruff, strict MyPy, all 182 backend tests, ESLint, Prettier, 0-error/0-warning Svelte type checking, all 21 frontend tests, and the production frontend build pass.
- Added read-only PEM-file secret mounting for local Compose, configured the locally created GitHub App, validated its RSA key, and ignored PEM files repository-wide to prevent accidental credential commits.
- Added an empty-access recovery state and server-derived GitHub installation management URL so a connected installation with zero granted repositories no longer appears to silently fail.
- Corrected authenticated Git smart-HTTP cloning to use GitHub's `x-access-token` Basic-auth convention instead of a REST-style Bearer header, and made retries discard only incomplete UUID-scoped repository caches left by failed clones.
- Added a server-verified GitHub installation identity endpoint and account/avatar presentation on both connection surfaces, so connected state identifies the user or organization that owns the installation.
- Simplified provider configuration lifecycle: credentials are verified automatically once after save, configured cards show the persisted verification result, and one page-level Refresh statuses action rechecks all credentialed connections on demand without continuous background API traffic.

## 2026-09-05 — Workflow-builder foundation

- Made each AI role's system prompt a persisted runtime setting with the safe built-in role contract retained as its fallback.
- Added an explicit per-role repository-knowledge policy and wired it into context compilation, allowing codebase RAG retrieval to be enabled or disabled independently for every worker.
- Replaced the agent-list framing with a single visual graph from deterministic Orchestrator through the AI roles to deterministic Deliverer; workflow nodes are selectable and expose live readiness.
- Added persistent manual knowledge sources scoped to each role. Text is chunked, embedded through the configured OpenAI embedding model, stored in pgvector, listed/deletable in the UI, and retrieved only for that role during execution.
- Added migration `0019_agent_knowledge` and REST operations for role knowledge lifecycle.
- Renamed the navigation entry from Agents to Workflow.
- Frontend lint, formatting, type checking, 21 unit tests, and production build pass. Backend Ruff, strict MyPy, and all 184 tests pass.

## 2026-09-05 — Durable drag-and-drop workflow designer

- Added the MIT-licensed Svelte Flow canvas behind a project-owned workflow component, with smooth node dragging, pan/zoom, minimap, animated routed edges, handle-based one-to-many and many-to-one connections, node/edge selection, and protected system nodes.
- Added agent palette controls for Intake, Thinker, Executor, Reviewer, and Tester plus deletion and editable edge outcomes.
- Added per-node activation policies (`any`, `all`, `required`, `manual`, and `batch`) to define fan-in behavior explicitly.
- Added a framework-free workflow graph domain, application use case/port, SQLAlchemy adapter, REST API, normalized PostgreSQL tables, and optimistic version conflict protection.
- Backend validation owns structural integrity: unique identities, allowed roles/outcomes/policies, exactly one Orchestrator and Deliverer, valid references, no self-routing, and reachability from Orchestrator to every enabled node and Deliverer.
- Added the Tester role to the persisted agent configuration model and PostgreSQL enum so it can be configured from the same role panel.
- Added domain tests for valid repair loops and invalid unreachable/protected/policy states.

## 2026-09-05 — Controlled live workspace console

- Added an xterm.js cloud-console modal with full interactive terminal input, ANSI rendering, resizing, scrollback, Vim-compatible PTY behavior, and explicit Ctrl+C delivery.
- Opening a console requires an active task workspace and an explicit manual takeover. The existing lifecycle pauses the task, cancels queued AI jobs, blocks new claims, emits takeover events, and rejects stale worker results.
- Added a safe-checkpoint gate that prevents a human PTY from sharing a writable workspace with a still-running agent process.
- Added short-lived one-time terminal access tokens stored only as SHA-256 hashes, managed-root path validation, bounded terminal dimensions/input/output/history, a minimal child environment, basic credential redaction, and explicit release/resume.
- Added durable PostgreSQL terminal session and audit-event tables behind an application port and use case, with a local PTY infrastructure adapter and authenticated WebSocket transport.
- Added live SSE-driven agent status refresh and a pulsing graph-node state while an agent is running.
- Added Git and Vim Tiny to the API image used by the controlled workspace console; Docker/host control is not exposed to the browser.
- Added terminal security unit tests; backend Ruff, strict MyPy, and all 190 tests pass. Frontend lint, formatting, type checking, unit tests, and production build pass.
# Workflow builder interaction and inspector redesign

- Replaced generic workflow boxes with purpose-built agent nodes showing role, core-agent identity, and live runtime state in a compact visual hierarchy.
- Added a persistent top-level **Add agent** menu; removed optional roles remain available there and can be restored to the canvas.
- Added a left-click agent action menu with **Edit configuration** and **Delete from graph** actions. Orchestrator and Deliverer remain visibly protected from deletion.
- Redesigned the agent configuration form as a focused inspector with Instructions, Model & cost, and Knowledge tabs, compact runtime metrics, status, enable control, save action, and live console access.
- Preserved workflow routing, drag/connect behavior, activation policies, model discovery, cost configuration, custom prompts, repository context, and manual vector knowledge.
- Refined canvas interaction conventions: single-click selects, double-click opens a status/details dialog, and right-click or the node's three-dot control opens Edit/Delete actions.
- Added persistent user-defined agent nicknames without changing stable backend role identity; nicknames are edited in the details dialog and saved with the workflow graph.
- Corrected graph route semantics: manually configured directional wires remain neutral regardless of their trigger condition, while bright animated cyan is reserved for a source agent that is actually processing. Trigger conditions are edited in the selected-route toolbar instead of being shown as misleading success/failure badges on idle wires.
- Removed the unnecessary workflow minimap so the compact graph no longer has a visually disconnected rectangle competing with its primary controls.
- Promoted user nicknames to the primary node heading and rendered the stable agent role separately. Nickname changes now persist on field commit as well as through the explicit node-save action.
- Enabled multiple non-core nodes of the same role, with automatic role-based numbering for default nicknames while preserving exactly one Orchestrator and Deliverer.
- Added durable per-node integration and repository-access selections to the workflow domain, API, database migration, and details UI. Intake/Deliverer expose configured integrations; AI nodes expose enabled projects and their RAG index status.
- Expanded workflow nodes to display their configured AI provider, exact model ID, integration icon chips (including recognizable Slack, Linear, and GitHub marks), and the number of projects granted RAG access.
- Made protected Orchestrator and Deliverer roles fully configurable through the same provider, exact model, system prompt, cost, repository-knowledge, and manual role-knowledge controls as other agents; graph protection now affects deletion only.
- Added true per-node AI configuration fields for provider, exact model, and system prompt plus durable model-validation status/message/timestamp. Node details can discover credential-authorized provider models, switch to manual model-ID entry, test availability, and display validation state directly on the graph.
- Added provider-switch safety that clears incompatible model IDs, explicit `NOT SET`/`UNVERIFIED`/`READY`/failure state labels on graph nodes, and real provider-catalog validation through a clean application port rather than accepting arbitrary text as valid.
- Applied workflow migrations through `0025_workflow_node_models` to the Dockerized PostgreSQL database and rebuilt the API, scheduler worker, and frontend. The deployed health check, workflow API, page response, and unconfigured-model validation path pass.
- Backend Ruff, strict MyPy, and all 193 tests pass. Frontend ESLint, Prettier, Svelte type checking, all 21 unit tests, and production build pass.

## 2026-09-05 — CI-only GitHub quality gate

- Simplified GitHub Actions to deterministic backend and frontend quality jobs; deployment/browser-environment validation is disabled until a stable deployment target exists.
- Backend CI checks Ruff lint and formatting, strict MyPy, the complete Alembic migration chain against pgvector/PostgreSQL, and all tests.
- Frontend CI checks ESLint, Prettier, Svelte/TypeScript typing, unit tests, and the production build.
- Formatted three older migration files that previously caused the repository-wide Ruff format gate to fail; all backend CI commands now pass locally with 193 tests.

## 2026-09-05 — Scheduled Linear task intake

- Added Intake-node trigger configuration for webhook-only, scheduled polling, hybrid webhook-plus-reconciliation, or manual operation.
- Added configurable polling intervals, discoverable Linear assignee selection, accepted Linear workflow-state filters, and visible reconciliation status/error/timestamp in the workflow graph inspector.
- Added a clean application reconciliation port/use case and a PostgreSQL-backed Linear adapter. Due schedules are claimed with row locks, retrieve matching assigned issues, idempotently create or update internal tasks, and queue Intake work only for newly imported tasks.
- Added durable external task snapshots containing the provider issue ID, identifier, assignee, state, synchronization timestamp, and complete provider payload for auditing and future field synchronization.
- Extended webhook intake to honor graph-owned assignee/state filters when configured while retaining the existing label-based fallback for unconfigured workflows.
- Added migration `0026_integration_schedules`; integration runtime status remains server-owned and is preserved across graph edits unless its schedule configuration changes.

## 2026-09-05 — Provider-aware task management board

- Replaced the flat task inventory with a responsive Linear-style workflow board covering backlog, active work, review, merge readiness, completed work, and attention-required states.
- Added compact provider-aware task cards and a rich slide-over detail view with description, assignee, creator, team, project, repository, estimate, due/created/updated/completed dates, labels, source status/link, and auditable raw provider data.
- Extended the clean task-query application port and PostgreSQL adapter with server-side title/ID, state, provider, repository, priority, created/updated/due date, assignee, team, project, label, and provider-state filtering plus deterministic sorting.
- Persisted provider-neutral due, started, and completed timestamps on tasks and populated them from both scheduled Linear reconciliation and webhook deliveries through migration `0027_task_management_fields`.
- Preserved the concurrently developed frontend localization and navigation work by limiting the task-board implementation to task-owned UI/service/type files.
- Backend Ruff, strict MyPy, and all 194 tests pass. Frontend ESLint, Svelte/TypeScript checking, all 23 unit tests, and the production build pass.

## 2026-09-05 — Backend transport dependency inversion

- Removed concrete SQLAlchemy, encrypted-provider, GitHub, Linear, repository, workflow, and worker adapter types from HTTP route signatures; routes now depend exclusively on application-layer protocols wired by the bootstrap composition root.
- Moved manual agent-knowledge list/create/delete operations out of the control-plane route's raw database session and behind a dedicated application use case, framework-free port, and SQLAlchemy adapter.
- Added an enforced architecture test preventing HTTP routes from importing SQLAlchemy, database models/sessions, integration clients, or persistence adapters, complementing the existing domain and application boundary checks.
- Preserved all endpoints and runtime behavior while establishing replaceable boundaries suitable for future team-scoped workflows, storage adapters, and queues.
- Backend Ruff, strict MyPy, and all 196 tests pass.

## 2026-09-06 — Multi-team execution foundation

- Added durable named teams with enable/pause state, per-team task concurrency, project/repository scope, timestamps, safe archival, and token/cost/queue/completion metrics.
- Added auditable task assignments with queue position, assignment reason, running/completed timestamps, safe reassignment checks, and a database-enforced terminal-state release invariant.
- Added load-aware task dispatching for dashboard and Linear webhook/polling intake. Eligible teams are selected by repository scope and normalized active queue load.
- Made workflow definitions team-owned while migrating the existing graph and all existing tasks into a backward-compatible Default team. Every new team receives an independent valid graph with collision-free node and edge identities.
- Enforced sequential work by default (`max_concurrent_tasks = 1`) with PostgreSQL-safe job claims, while allowing independent teams to claim and execute tasks in parallel.
- Workers now resolve provider, exact model, system prompt, and repository permission from the assigned team's workflow node, retaining the legacy agent configuration only as a compatibility fallback.
- Added clean-architecture team domain objects, application ports/use cases, persistence adapters, REST CRUD/assignment/graph/model-validation APIs, and team-domain tests.
- Added a Teams UI with queue/activity/token/cost visibility, team creation/editing/archival, concurrency policy, repository/RAG scope, and links into the existing drag-and-drop workflow editor in team context.
- Migration `0028_teams` applied successfully to Dockerized PostgreSQL; the existing workflow was preserved at version 11 under Default team.
- Backend Ruff, strict MyPy, and all 199 tests pass. Frontend ESLint, Svelte/TypeScript checking, all 23 unit tests, and production build pass.

## 2026-09-06 — Team assignment and manual-task UX

- Dashboard creation now produces explicitly manual, unassigned tasks without starting agents.
- Task management displays the assigned AI team with a stable visual identity, filters by a specific team or Unassigned, and supports assignment, reassignment, and safe unassignment.
- Assigning an idle manual task creates its Intake job; moving or removing it cancels stale queue ownership while refusing to interrupt a running agent.
- External tracker teams remain separate from internal AI-team assignees in filters and task details.
- Team cards and configuration actions were visually tightened, including clearer edit and save/cancel controls.
- Default and newly created workflow graphs include Tester between Reviewer and Deliverer; migration `0029_default_team_tester` upgrades existing installations.

## 2026-09-06 — Per-agent advanced execution controls

- Added persisted node-level reasoning effort, optional output-token limit, capability-aware temperature, timeout, retry limit, review/fix-cycle limit, context depth, RAG retrieval depth, and optional fallback provider/model configuration.
- Added an Advanced execution settings panel to every graph agent, with role-relevant controls and an Enabled switch.
- Disabled nodes are visibly muted and excluded from runtime model resolution and integration intake queries.
- Worker execution now applies output limits, temperature, reasoning effort, provider-request timeout, structured-output retries, context-size presets, and RAG retrieval-count presets.
- Added migration `0030_agent_execution_settings` and validation bounds across the domain and API schemas.
# 2026-09-06 — Reusable Role contracts and concrete team agents

- Added a framework-free Role domain with normalized categories, capabilities, permission catalogues, validation, and role/job compatibility rules.
- Added application ports/use cases plus SQLAlchemy adapters for listing, reading, creating, editing, cloning, disabling, and soft-deleting Roles.
- Added immutable built-in templates for Orchestrator, Intake, Thinker, Executor, Reviewer, Tester, and Deliverer. Built-ins can be cloned but not silently mutated or removed.
- Added concrete `ai_agents` records scoped to Teams and linked workflow nodes to those agents without breaking existing workflow behavior.
- Added migration `0031_roles_and_agents`, including backfill of existing team workflow nodes into concrete agents.
- Worker configuration now resolves platform instructions + current Role version + concrete Agent instructions/model settings, records that immutable identity/configuration on every worker run, and rejects incompatible Role capabilities.
- Enforced Role permissions at runtime boundaries for repository reading, repository writes, test execution, and RAG retrieval. Agent overrides can remove inherited permissions but cannot grant permissions absent from the Role.
- Added the `/api/v1/roles` management API and permission/capability catalogues.
- Added a dedicated Roles UI with reusable templates, custom Role creation/editing/cloning/deletion, prompts, capabilities, permissions, allowed structured results, and advanced model defaults.
- Added Roles to desktop/mobile navigation and English/Georgian navigation labels.
- Verified migration `0030 -> 0031` against the live Docker PostgreSQL database; the Role API and `/roles` page both return successfully.
- Validation: backend Ruff and mypy pass; backend test suite has 203 passing tests. Frontend lint, Prettier, Svelte typecheck, 23 unit tests, and production build pass.

## 2026-09-06 — Live engineering control-center dashboard

- Replaced the placeholder home screen with a responsive cockpit-style operations dashboard backed exclusively by persisted or measured state.
- Added global system health, active-task, full queue, merge-ready, AI-token, estimated-cost, autonomy, and human-attention metrics with Today/7-day/30-day ranges.
- Added current-worker identity and runtime, team activity cards, the single-lane scheduler queue, recent task activity, task-throughput history, and AI usage grouped by Role.
- Added explicit dependency health for PostgreSQL, configured GitHub/Linear/AI providers, repository RAG freshness, and worker heartbeat state. Unconfigured services remain visibly distinct and do not falsely degrade system health.
- Added live host CPU, RAM, disk, load-average, and uptime telemetry through a replaceable application port and a `psutil` infrastructure adapter; high-frequency samples are not written to PostgreSQL.
- Dashboard queries live behind a clean application protocol/use case and a SQLAlchemy read adapter. The HTTP layer contains no persistence imports.
- The dashboard hydrates through REST, subscribes to the existing SSE event stream, refreshes relevant aggregates after events/reconnection, and polls only ephemeral host telemetry.
- Corrected queue reporting so the headline total is not truncated by the 25-row display limit, and added deterministic Team states for working, waiting externally, paused, failed, human-needed, and idle conditions.
- Reordered backend Docker system-package layers so source-only rebuilds retain the expensive `apt` cache.
- Validation: backend Ruff and strict mypy pass; all 203 backend tests pass. Frontend ESLint, Prettier, Svelte/TypeScript checking, all 23 unit tests, and production build pass.

## 2026-09-06 — Manual task creation in Task Management

- Added a dedicated `Create manual task` dialog to the Task Management board instead of coupling task intake to the operational dashboard.
- Manual tasks support title, description, priority, reference key, repository, project, estimate, due date, normalized labels, and optional immediate AI-team assignment.
- Creation is deliberately non-running while unassigned; selecting a Team uses the existing assignment workflow to create the Team-owned Intake job safely.
- Added provider-neutral project, label, and estimate storage to Tasks through migration `0032_manual_task_properties`, preserving those fields independently of Linear/GitHub snapshots.
- Manual properties are returned by task queries, displayed on board cards/details, and included in project/label filters alongside external-provider metadata.

## 2026-09-06 — Fresh-database migration reliability

- Corrected historical PostgreSQL enum migrations to commit newly added enum values before later revisions use them in data backfills or runtime constraints.
- Covered `MERGED`, `CONTEXT_PENDING`, `TESTER`, `ORCHESTRATOR`, and `DELIVERER` instead of fixing only the first value reported by CI.
- Reproduced the GitHub Actions database path against an isolated empty PostgreSQL database and successfully applied the complete `0001 -> 0032` Alembic chain.

## 2026-09-06 — Autonomous execution policy and Tool Gateway foundation

- Added deterministic `ALLOW` / `DENY` / `REQUIRE_HUMAN` policy evaluation with Autonomous, Conservative, and Custom Team modes. Platform hard-denies override user configuration.
- Expanded the Role capability catalogue for filesystem, shell, build/lint/test, Git/task-branch, GitHub, task-management, knowledge, and network operations; legacy permissions resolve to their narrower runtime equivalents.
- Added canonical workspace path enforcement with traversal, sibling-prefix, symlink, Windows drive, separator, and case-insensitive ancestry coverage.
- Added an audited Tool Gateway for writes, creates, deletes, bounded shell execution, and task-branch push authorization. Executor file changes and validation commands now pass through it.
- Added hard denial for privilege/system/container-management commands and Docker daemon access, direct executable execution, non-interactive environments, command timeouts, cross-platform process-tree termination, output caps, and secret sanitization.
- Added persistent Team execution policies, exact-argument approval requests with expiry/one-time consumption, and sanitized tool execution events through migration `0033_execution_policy_gateway`.
- Added policy, approval, and task/job audit APIs; Team configuration now exposes execution modes/capability decisions, while the dashboard exposes pending approvals with Allow Once and Deny actions.
- Strengthened platform agent instructions around untrusted external content, non-escalation, non-self-modification, routine autonomy, and deterministic runtime authority.
- Validation: strict backend formatting/lint/typing passes with 213 tests; frontend lint, formatting, Svelte/TypeScript checks, 23 tests, and production build pass.

## 2026-09-06 — Backend safety and duplication audit

- Audited backend modules, imports, subprocess entry points, filesystem mutations, and legacy
  adapters. No module was deleted without reliable proof that runtime entry points do not use it.
- Centralized execution-policy invariant validation in the domain object so API, worker, and
  persistence callers share the same capability and runtime-limit rules.
- Prevented command-specific environments from replacing the Tool Gateway's protected `HOME`,
  `PATH`, or Windows `USERPROFILE`, and create a private worker home before execution.
- Added regression coverage for invalid capabilities, invalid limits, and protected worker
  environments.
- Validation: backend formatting, Ruff, strict mypy, and all 219 tests pass.
