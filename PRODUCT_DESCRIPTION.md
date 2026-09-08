# Autonomous Engineering Worker — Complete Product and Architecture Reference

Status: implemented engineering control plane with local deployment and validation support  
Deployment: one trusted Linux server with Docker Compose; Docker Desktop for development  
Core rule: models produce engineering work; deterministic code owns authority, safety, accounting, validation, publication, and merge

## Product purpose

Autonomous Engineering Worker receives authorized engineering work, runs one primary native coding harness in an isolated checkout, validates source independently, publishes a branch and pull request, waits without model activity, applies authorized feedback through the same logical Developer session, and merges only when the current revision satisfies configured gates.

The product also reports live and historical infrastructure health, task and agent efficiency, AI usage and cost, resource attribution, incidents, and statistical forecasts. Monitoring and analytics cannot authorize work, spend money, mutate lifecycle state, or prevent an otherwise healthy Developer task.

The system has three operational planes:

- Control: FastAPI, PostgreSQL, controller, integrations, authorization, lifecycle, accounting, policy, delivery, and merge.
- Execution: ephemeral Developer, validator, and publisher containers; native Codex or Claude harness; optional local Interpreter.
- Observation: Prometheus, exporters, Alertmanager, typed query adapters, durable summaries, analytics, and Svelte dashboard.

There is one application, one fixed lifecycle, one `/api` product prefix, and one PostgreSQL application database. Prometheus is a private time-series store, not a second business database.

## Responsibilities and boundaries

The application:

- receives work from manual entry, Trello, Linear, Slack, GitHub issues, and review events;
- verifies signatures, delivery identity, actors, eligibility, and repository scope;
- routes obvious events deterministically and interprets only ambiguous bounded text;
- persists versioned task requirements and lifecycle state;
- maintains one logical native Developer session per task generation;
- creates isolated worktrees and constrained runners;
- reserves and reconciles paid usage against Team and task limits;
- runs administrator-defined validation outside the model session;
- commits, publishes, and records exact revision evidence;
- waits for checks and review without model activity;
- resumes the logical Developer with feedback deltas;
- merges only after current-revision policy and evidence checks;
- synchronizes source trackers through a durable outbox;
- records usage, cost, time, recovery, review, and resource evidence;
- forecasts cost, tokens, time, and resources without paid forecasting calls.

The product excludes arbitrary workflow graphs, user-defined role types, mandatory planning/testing/review model chains, repository retrieval as a coding prerequisite, model-controlled Git or merge authority, public monitoring interfaces, hosted monitoring requirements, and an extra custom service language without measured need.

## Fixed delivery lifecycle

```text
authorized source event
  -> deterministic intake
  -> bounded interpretation only when needed
  -> engineering task
  -> native Developer in isolated checkout
  -> offline deterministic validation
  -> validated local commit
  -> credentialed branch publication and pull request
  -> review wait with zero AI activity
  -> code feedback: resume logical Developer
  -> approval: evaluate exact-revision merge gates
  -> revalidate and republish when changed
  -> guarded merge
  -> durable tracker completion
```

Statuses are `NEW`, `ACTIVE`, `WAITING_EXTERNAL`, `WAITING_HUMAN`, `PAUSED`, `FAILED`, `CANCELLED`, and `MERGED`. Stages are `INTAKE`, `PLANNING`, `DEVELOPING`, `VALIDATING`, `PUBLISHING`, `REVIEWING`, `FIXING`, `MERGING`, and `COMPLETE`.

Status, stage, wait reason, requirement revision, and lifecycle revision are independent. Pausing retains the checkout, native state, accounting, and phase. Late results cannot advance newer state. Requirement changes invalidate stale validation and approval evidence.

## Intake and integrations

All adapters create normalized events. Intake verifies provider signatures, delivery deduplication, actor authorization, source routing, and repository scope before changing state. Free text is bounded and never grants authority.

- Trello: a signed webhook wakes authoritative card reconciliation; configured board/list and actor rules determine eligibility and status destinations.
- Linear: configured assignee and source-state identifiers determine work; assignment/state events are deterministic.
- Slack: signed Events API callbacks route configured workspace/channel pairs; task commands create work and deterministic thread relationships attach replies.
- GitHub: issue, pull-request, review, comment, and check events are verified and deduplicated; authoritative remote state is fetched before publication and merge.

Formal checks and approvals are deterministic. Natural-language review may use the bounded Interpreter. Uncertain output waits for an operator rather than guessing.

## Teams and policy

Each Team has fixed `INTERPRETER`, `DEVELOPER`, `THINKER`, and `REVIEWER` profiles. Interpreter and Developer are core roles; Thinker and Reviewer are optional. Operators configure display identity, provider, model, harness, reasoning effort, fallback, repository scope, concurrency, budgets, and optional-role enablement. They cannot create role kinds or change lifecycle topology.

Automation policy is versioned and audited. It controls enrollment, repositories, task and Team spending, reviewer actors, checks, approval semantics, and automatic merge. Stopping a Team revokes active leases and pauses work without erasing usage. Enabling it again does not silently resume paused tasks.

## Native Developer runtime

The harness owns source discovery, reads and edits, tools, model conversation, provider session state, compaction, and usage receipts. The platform owns lifecycle, workspace, cost admission, container policy, validation, Git operations, authorization, and audit.

The provider-neutral adapter exposes supported start, resume, interrupt, compact, inspect, and seal operations through capability flags. Unsupported provider behavior is explicit rather than simulated.

A `DeveloperSession` records task, profile, harness, provider, model, native identifier, workspace/state locations, requirement revision, current revision, checkpoint, and timestamps. Review repairs send only new feedback. Missing native state blocks execution; the system never invents continuity.

### Context generations and checkpoints

A logical session can use several bounded physical contexts. Code continuity lives in the checkout and Git state, authoritative continuity in PostgreSQL, and unresolved intent in a bounded checkpoint. A fresh context receives stable instructions, current requirements, verified checkpoint, workspace, and next action—not the prior transcript.

Before rollover, the controller verifies task and requirement revision, checkout fingerprint, Git-derived changes, bounded checkpoint schema, billing reconciliation, lease or suspension state, and allowance. It atomically persists checkpoint and generation transition, seals the prior context, retains its native identifier, and requires the new context to acknowledge the checkpoint digest before write access.

## Token efficiency

Token control surrounds the same Developer; it does not add an agent chain. The system distinguishes cumulative task usage, native-run usage, active-context estimate, and tokens since useful progress.

Available telemetry includes input, cached input, cache creation, output, reasoning, cost, duration, context generation, compactions, time to first tool/edit, tool counts, source/shell bytes, repeated reads/commands, diff changes, targeted-check transitions, active-context peak, and measurement quality. Unknown values remain null. Provider-defined subsets are not counted twice.

`FAST`, `STANDARD`, and `LARGE` are execution-policy presets. They configure reasoning, first-edit warning, exploration/no-progress limits, active-context ceilings, repetition thresholds, compaction/rollover limits, and model-visible tool output. Task overrides require safe suspension.

Policy modes:

- `INSTRUMENT` records evidence only.
- `WARN` injects each relevant bounded warning once.
- `ENFORCE` interrupts confirmed exploration, no-progress, repeated-tool, repeated-failure, or context-limit conditions.

Useful progress includes first edit, changed diff fingerprint, improved check, changed diagnosis, completed milestone, advanced checkpoint, or completion. Status checks, unchanged rereads, and identical failures are not progress. Enforced stops preserve evidence and do not purchase replacement runs automatically. USD limits remain authoritative and usage never resets.

Noisy commands use a bounded wrapper. Full output stays in protected task storage with digest, size, timing, status, and ownership; the model receives summary, highlights, bounded tails, a truncation marker, and log handle. Credentials are stripped from wrapped environments and timeouts terminate the process group.

## Cost and accounting

PostgreSQL `ai_runs` is billing truth. Prometheus counters are operational mirrors.

Receipts store provider, model, harness, role, run kind, native identifiers, task/session/job, requirement and context generation, token categories, reported or calculated cost, reservation, pricing record, timings, status, usage completeness, bounded artifact, normalized raw usage, and efficiency evidence.

Before paid work, the controller locks Team admission, totals known and reserved spend, checks the price catalog and hard limits, creates a reservation, and persists the native identifier before inference. Completion reconciles actual usage. Unknown interrupted cost blocks more spending until explicitly reconciled with evidence. Provider account limits remain a second defense.

Totals are complete only when required measurements are known. Cost per merged task excludes incomplete tasks and reports exclusions. Failed, reserved, compaction, and local-inference spend remain separate.

## Isolation, validation, publication, and merge

### Developer runner

The runner uses a non-root user, read-only root filesystem, task checkout and native-state mounts, read-only controller acknowledgment, task lock, dropped capabilities, no Docker socket, no database or GitHub credentials, restricted provider egress, explicit CPU/RAM/PID limits, and disabled subagents by default.

Repository runtime profiles specify Developer and validator images, validation argv, image digest, and verification timestamp. Required dependencies are baked into images before execution.

### Validation

Validation is model-free in a separate container. Commands are administrator-owned argv arrays without shell concatenation. Network and sensitive credentials are absent. Output and time are bounded, process groups are terminated on timeout, validation-created changes are detected, and exact fingerprint/revision evidence is stored. Success creates the validated commit.

### Publication

The publisher runs fixed Git operations in a clean repository with hooks disabled. It accepts only the task branch format, does not force-push, verifies expected objects and base/head, looks up an exact pull request before creation, and reconciles ambiguous writes from GitHub state. The model cannot select arbitrary Git authority.

### Merge

Merge requires enabled policy, allowed repository, pull-request head equal to validated revision, validation for current requirements, configured checks present and green, authorized current-revision approval, no blocking change request, confirmed mergeability, unpaused task/Team, and an expected-head merge request. Changes trigger revalidation and invalidate stale evidence.

## Backend ownership and persistence

The Python backend is a modular monolith:

- `engineering`: lifecycle, controls, requirements, phases, and jobs;
- `agent_runtime`: native adapters, sessions, usage, context policy, checkpoints, and generations;
- `intake`: events, authorization, deduplication, routing, and interpretation;
- `delivery`: validation, branch/PR identity, review, merge, and tracker outbox;
- `teams`: profiles, automation, budgets, scope, assignment, and concurrency;
- `repositories`: inventory and runtime profiles;
- `observability`: typed metrics, attribution, summaries, availability, and incidents;
- `analytics`: efficiency, forecasts, and accuracy;
- `platform`: configuration, database composition, integration storage, scheduling, and telemetry;
- `interfaces/http`: transport validation and errors;
- `bootstrap`: dependency and scheduler composition.

Domain modules do not import web frameworks, ORM, Docker, or provider SDKs. Application services depend on protocols and domain values. Infrastructure implements persistence and external boundaries.

One PostgreSQL database contains settings, integrations, Teams, profiles, automation, repositories, tasks, messages, events, snapshots, assignments, jobs, phases, sessions, contexts, checkpoints, token policy, AI/local receipts, prices, validations, reviews, webhook delivery, status outbox, workers, monitoring settings, runtime profiles, runner bindings/summaries, infrastructure observations/events, incidents, and forecasts.

Alembic revisions are schema mechanics, not product editions. Raw Prometheus samples are not copied into PostgreSQL.

## Observability and resource attribution

Prometheus stores operational time series and evaluates alerts. cAdvisor reports container resources. Node Exporter reports Linux host data. PostgreSQL Exporter uses a dedicated monitoring role. Blackbox Exporter probes frontend/backend reachability without triggering model usage. Alertmanager sends actionable alerts to an authenticated internal incident endpoint. Grafana is optional and never required by the product.

Metrics labels exclude descriptions, source, prompts, messages, review text, credentials, arbitrary exceptions, task IDs, pull-request numbers, commits, and provider threads. cAdvisor container identity joins to domain IDs through PostgreSQL rather than multiplying time-series labels.

The Docker-owning controller writes runner bindings joining container and host to task, Team, profile, role, phase, timestamps, exit, and out-of-memory state. After exit, fixed range queries persist coverage, CPU/throttling, average/peak/percentile memory, network, block I/O, process maximum, out-of-memory, restart, and completeness. Missing coverage remains incomplete.

Docker create, start, health, restart, die, out-of-memory, kill, and destroy events are stored with bounded metadata and no full environment/command line. Durable incidents cover unavailable, degraded, restart loop, out-of-memory, database pressure, disk pressure, and queue stall.

Prometheus, exporters, alerts, dashboards, and forecasts may fail independently; data becomes unavailable or stale and execution continues. Missing probe samples are not downtime. PostgreSQL failure is different: durable execution fails closed.

## Analytics and forecasts

Analytics reads durable facts and aggregated operational data without lifecycle mutation. It reports known/unknown cost, tokens, turns, compactions, Interpreter calls, failures, rate limits, merge/success/intervention rates, percentile cost/time, tokens per merged task, failed spend, repair/validation cycles, and wait reasons. Developer active time, provider time, check/review wait, and human wait remain distinct.

Forecasts make no paid AI calls. They estimate task and queue tokens, cost, Developer time, engineering time excluding human review, peak memory, queue drain, and period spend. Cohorts fall back from repository+harness+model+complexity to broader Team/global evidence. Responses include estimate, range, confidence, sample count, and forecast identifier.

Forecast snapshots are written before execution and actuals finalized separately. Predictions are never overwritten after outcomes. Accuracy includes median percentage error, range coverage, bias, runtime error, and resource error. Resource-aware admission remains advisory until enough representative data proves it reliable, then remains independently feature-flagged.

## Product API

All product endpoints use `/api`; raw PromQL is never accepted from the browser.

- `/api/tasks`: create/detail, controls, notes, events, jobs, validation, receipts, session changes, token policy/evidence, resources, forecasts, and export.
- `/api/teams`: management, assignment, stop/wake, profiles, automation, activity, and token policy.
- `/api/repositories`: discovery, inventory, enablement, scope, images, and validation commands.
- `/api/integrations`: configuration, credential verification, metadata, and synchronization.
- `/api/dashboard`: control-center summaries and telemetry.
- `/api/observability`: live snapshots, history, availability, incidents, and authenticated alert ingestion.
- `/api/analytics`: AI, agent, model, task, queue, period, and forecast accuracy.
- `/api/events/stream`: lifecycle refresh.
- `/api/settings`: presentation and monitoring preferences.

Operational paths are `/health/live`, `/health/ready`, `/metrics`, and signed `/webhooks/*`. Caddy blocks public metrics and alert ingestion. Provider-controlled protocol paths are external contracts, not product API editions.

## Frontend

The SvelteKit operator console uses one API helper and typed services. The dashboard contains selective CPU/RAM/budget/disk gauges, a service leaderboard, AI cost and efficiency, agent comparison, forecasts, reliability, incidents, and active runners. Exact values accompany gauges; trends use lines, comparisons use tables/bars, and missing data is visibly unavailable.

The Team page has a fixed read-only lifecycle canvas with current task, model, tokens, cost, resources, and elapsed time. Waiting stages show zero AI activity. Task detail exposes overview, execution, receipts, token efficiency, resources, review, incidents, and forecast-versus-actual evidence.

Lifecycle changes use server-sent events. A single live overview request populates top-level resources. Common aggregates are briefly cached, historical queries load only when visible, and polling pauses with hidden tabs where practical. The ECharts wrapper handles client initialization, resize, updates, disposal, reduced motion, theme, and adjacent accessible text.

## Deployment and configuration

The Compose project runs PostgreSQL, backend, controller, frontend, provider gateway, Prometheus, cAdvisor, Node Exporter, PostgreSQL Exporter, Blackbox Exporter, and optional Alertmanager/Ollama. Developer, validator, and publisher containers are ephemeral.

`compose.yaml` is the local base. `deploy/compose.production.yaml` is the Linux/TLS base. `deploy/compose.execution.yaml` adds native execution. `deploy/compose.observability.yaml` adds monitoring; the desktop overlay adapts host collectors locally.

The native SDK base and repository-ready runner image are separate so rebuilding the base cannot erase locked repository dependencies. Production images should use verified immutable digests.

Caddy joins ingress/application networks. The controller has only required networks plus Docker authority. Ollama and monitoring are private. Backend joins monitoring only to query Prometheus. Developer runners never join it and reach providers only through restricted egress. Monitoring/Ollama/Docker ports are not published.

Operators configure one synchronous/asynchronous URL pair for the same database, secrets, GitHub App identity, absolute execution data root, runner images, harness flags, validation argv, scheduler limits, price catalog, Team budgets, source routes, reviewer/check policy, and optional monitoring tokens/retention/thresholds. Paid harnesses and scheduling default off until admission prerequisites pass.

## Startup and checks

Copy `.env.example` to ignored `.env` and configure it. Start the selected stack:

```sh
docker compose up -d --build --wait
```

Start only the local base:

```sh
docker compose -f compose.yaml up --build postgres backend frontend
```

Backend checks:

```sh
cd backend
make check
```

Frontend checks:

```sh
cd frontend
npm run check
npm run test:e2e
```

Database integration uses `TEST_DATABASE_URL`. Migration checks can use isolated schemas; suites that intentionally mutate credentials require an isolated test database. `scripts/start-local.sh` starts the configured local stack. The workflow observer is read-only. The observability verifier exercises metrics and incidents without paid work.

## Failure, recovery, and security

- Native identifier persistence failure stops before inference.
- Missing usage remains unknown and blocks spending according to policy.
- Checkpoint failure retains the current context and stops without paid retry.
- Compaction failure is bounded; rollover requires a verified checkpoint.
- Fresh-context failure retains the sealed context and checkpoint.
- Lost continuity blocks writes until task, requirement, workspace, and digest agree.
- Validation failure returns bounded evidence without network or merge authority.
- Ambiguous GitHub writes reconcile from authoritative remote state.
- Stale approval, changed revision, missing checks, conflict, pause, or blocking review prevents merge.
- Controller restart recovers leases, containers, sessions, and durable jobs using stable identifiers.
- Monitoring failure has no execution authority.
- Database failure stops durable work rather than proceeding from memory.

Only the controller has Docker authority. API/frontend lack the socket. Developers lack database/GitHub credentials. Validators lack network/provider credentials. Publisher authority is bounded. Model output cannot change policy, budgets, authorization, validation commands, or merge evidence. Integration credentials are encrypted and scoped. Monitoring uses dedicated secrets. Logs/native state remain protected. Exact actor, repository, task, requirement, and revision checks guard external actions.

## Retention and performance

Host/container scraping is approximately ten seconds, application/database scraping fifteen seconds, and availability probing thirty seconds. Prometheus retention is bounded by time and disk size. Summaries, incidents, AI usage, tasks, and forecasts remain durable in PostgreSQL.

Live snapshots and aggregates use bounded caches. Historical requests are keyed by typed metric/range/step. Prometheus response size, points, concurrency, timeout, malformed data, warnings, non-finite values, and cardinality are bounded. Monitoring services have CPU, memory, and process limits.

## Acceptance criteria

Automated acceptance covers domain/application rules, adapters, migrations, persistence, lifecycle, leases, accounting, session changes, bounded output, security, API contracts, frontend unit/build behavior, browser flows, Compose configuration, exporter configuration, and unpaid native startup/isolation.

Production acceptance additionally requires representative authorized tickets: small UI, documentation/configuration, backend rule, initial validation failure, review repair, pause/resume, provider failure, stale approval, and merge conflict. Each records completion, pull request, merge, intervention, token categories, cost, Developer/wall time, turns, compactions, contexts, review/validation cycles, peak memory, CPU, and recovery.

Token optimization is judged by completed-task rate, median and high-percentile total/uncached input, peak active context, cost, intervention, and wall time. Monitoring overhead is measured on the same workload enabled and disabled. Passing local checks does not establish provider invoice accuracy, universal cost savings, unattended reliability, or every-repository support; those claims require recorded real-task evidence.

## Final operating rule

The checkout remembers code. PostgreSQL remembers authoritative state, policy, accounting, evidence, and continuity. A bounded checkpoint remembers unresolved intent. Native context carries only the current slice. Models implement and reason; deterministic code retains authorization, spending, validation, publication, and merge authority.
