# Autonomous Engineering Worker — Complete Product and Architecture Reference

Status: implemented engineering control plane with local deployment and validation support  
Deployment: one trusted Linux server with Docker Compose; Docker Desktop for development  
Core rule: models produce engineering work; deterministic code owns authority, safety, accounting, validation, publication, and merge

## Product purpose

### Current MVP execution path

The configured test workflow uses Luna for bounded supervision and Terra LOW through
the `patch` Developer harness. The patch pipeline localizes existing source, requests
one complete multi-hunk patch, applies it deterministically, and runs targeted checks.
`FAST_PATCH` permits at most one model repair: two Developer model calls per fast attempt.
Full offline validation, publication, review, and merge remain separate gated stages.

The same harness also supports adaptive bounded execution. Supervisor annotations select
`STRUCTURED_MULTI_PATCH` for decomposable work or `BOUNDED_AGENTIC` for uncertain
localization/root cause; ordinary tasks remain fast patches. Complex/high-risk task
classification requests a plan rather than selecting an unbounded coding harness.
A fast response that explicitly reports insufficient context may escalate once into
planning; a pre-model localization failure may enter bounded investigation.

Multi-patch execution makes one structured planning request, validates an acyclic graph
of at most six units, and runs those units sequentially in the existing isolated checkout.
Each unit gets current hashed source, original requirements, integration invariants and
compact prior results—not previous conversations. Each unit permits one patch and one
repair. Intermediate checks format/lint; frontend-wide typechecking is deferred until
all units are assembled. Integration permits one extra bounded repair when the relevant
scope fits a three-file packet, then requires all developer checks to pass before handing
off to the unchanged full validator. This does not prove UI behavior or Tauri build quality:
the repository's configured full validation must cover those surfaces where required.

Investigation is read-only and limited to two structured requests with a bounded repository
search and batch of at most three source reads between them. It must produce findings before planning;
it has no shell, edit, GitHub or merge tool. No hosted JavaScript tool runtime is needed.
All adaptive requests share the existing turn cost/input allowance and a ceiling of
16 calls, including any preceding fast attempt. Planning/investigation request medium
effort subject to the Team ceiling; patching stays low. The configured Developer model
and its verified pricing remain unchanged—there is no silent model-tier escalation.

Plans, requests, usage, work-unit results, source hashes and check logs are durable runner
artifacts. Requests are persisted before admission. A resumed already-attempted generation
does not repeat paid calls, including after a crash with unknown usage; inspection or an
explicit fresh-generation workflow is required. Exhausted recovery remains a visible stop,
not an automatic budget reset. Live Execution displays mode, phase and completed unit count.

Localization uses a SHA/content-keyed repository index and bounded source packets.
Tree-sitter covers Python, JavaScript, TypeScript and Svelte scripts; other supported
text files use lexical matching. Imports, callers and related tests are candidates,
not a complete type-resolved dependency graph. Relative JS imports and unambiguous Python
module imports have resolved dependency paths. Large required files use bounded, task-ranked
source ranges with whole-file hashes; omitted lines are explicitly marked unknown.
Patch scope is limited to up to three files per unit, with source and patch size ceilings.
Work plans may explicitly declare new non-executable text files in existing source
directories; application verifies they do not already exist. Deleting/renaming files,
creating directories and installing dependencies remain unsupported. Insufficient localization
or exhausted repair attempts can still require human attention.

Native Codex, Claude and the frontend-scoped Responses tool loop remain selectable
alternatives. Selecting Responses does not select the two-call patch pipeline.
Its compound tools batch deterministic work; it is not hosted programmatic JavaScript
tool calling. Model, effort and harness selection remain Team/profile configuration,
not an automatic model-capability fallback ladder. Adaptive patch composition never switches
to those open-ended coding harnesses automatically. Parallel units, cross-repository plans,
automatic stronger-model routing, visual evaluation and broader framework adapters remain
future work, not claims about this rollout.

### Bounded Supervisor

`SUPERVISOR_ENABLED=true` enables one bounded Luna supervision request before each
Developer job, including repair jobs. The Supervisor receives the current requirement,
feedback, bounded repository inventory/entry-point evidence and unverified filename matches.
Fresh intake does not replay a previous failed interpretation as authoritative memory.
It returns advisory annotations (object, operations, preserved behavior, assumptions)
or an essential clarification request. The verbatim original requirement takes precedence.
Self-reported confidence is not an authorization or escalation gate.

The request uses existing Team/task spending admission with an additional per-request
ceiling (`SUPERVISOR_REQUEST_LIMIT_USD`, default $0.02). Configure verified catalog
pricing for `SUPERVISOR_MODEL` (default `gpt-5.6-luna`). Its receipt appears as SUPERVISOR
in AI usage and its decision as SUPERVISOR_DECIDED in task events. Job payloads retain
the attempt ID and decision; native session checkpoints retain bounded semantic memory.
An attempted request without a valid saved decision is not automatically repurchased.
Provider usage is retained even when decision parsing fails; unavailable usage stays unknown.

Codex additionally reports selected failed tools or sustained no-progress evidence,
at most twice per job. Each deduplicated, metered Supervisor decision can continue,
steer the existing turn, or stop it. Delivery is best-effort if the native turn finishes
while a decision is pending; a late annotation never starts another paid run.
Normal tool success does not wake the Supervisor. Additional request headroom is
deducted from the Developer allowance, not added on top of Team/task budgets.
The first no-edit checkpoint is triggered at three observed inference cycles or 40k
input tokens. Its compact response is continue, narrow scope, edit now, infrastructure
problem or escalate. The STANDARD exploration hard stop defaults to 110k, separately
from this early intervention; existing persisted Team policies remain operator-controlled.
The runner's investigation helper indexes Python/JavaScript/TypeScript and Svelte
script symbols with Tree-sitter, imports, references, routes and entity declarations.
The cache key includes Git SHA and source hashes so uncommitted edits invalidate it.
It returns up to five candidates and bounded relevant slices. Caller/test associations
are syntactic candidates, not type-resolved LSP claims. The installed frontend formatter
resolves its working directory and plugins independently of the shell working directory.
Developer profile effort is preserved, capped by Team policy; only an explicit task
override can raise it. Token/loop/runtime stops have distinct wait reasons.

This MVP preserves the current coding harness, validation and delivery transitions.
Repair jobs in FIXING create a fresh native context once per job, on the same checkout,
with original requirements, SHA, diff summary, exact feedback and latest validation.
Old receipts and costs remain intact. No-progress interruptions do not auto-restart.
When supervision is enabled, natural-language GitHub review classification also uses
the task Supervisor's bounded memory and policy. Obvious controls and authoritative
checks remain deterministic. Automatic model escalation and Claude live supervision
are not implemented. This is not a general AI-owned lifecycle engine: the fixed
state machine and authorized action handlers still control transitions.
Disable the flag to bypass supervision for subsequent jobs. Existing task/Team pause
controls revoke the job lease, including an in-flight supervision request. No model
calls occur during review waits. Token savings require measuring new tasks; they are
not guaranteed by adding the Supervisor.

Autonomous Engineering Worker receives authorized engineering work, runs the configured Developer harness in an isolated checkout, validates source independently, publishes a branch and pull request, waits without model activity, applies authorized feedback through a bounded repair generation, and merges only when the current revision satisfies configured gates.

The product also reports live and historical infrastructure health, task and agent efficiency, AI usage and cost, resource attribution, incidents, and statistical forecasts. Monitoring and analytics cannot authorize work, spend money, mutate lifecycle state, or prevent an otherwise healthy Developer task.

The system has three operational planes:

- Control: FastAPI, PostgreSQL, controller, integrations, authorization, lifecycle, accounting, policy, delivery, and merge.
- Execution: ephemeral Developer, validator, and publisher containers; patch, Responses, Codex or Claude harness; optional local Interpreter.
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
  -> configured Developer in isolated checkout
  -> offline deterministic validation
  -> validated local commit
  -> credentialed branch publication and pull request
  -> review wait with zero AI activity
  -> code feedback: bounded repair on the same checkout
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

Formal checks and approvals are deterministic. Natural-language review uses the bounded Supervisor when enabled, with the Interpreter path retained when supervision is disabled. Uncertain output waits for an operator rather than guessing. A deterministic review reconciliation job checks remote state approximately once a minute; unchanged review waits do not invoke a model.

## Teams and policy

Each Team has fixed `INTERPRETER`, `DEVELOPER`, `THINKER`, and `REVIEWER` profile records. Thinker and Reviewer are reserved profiles; optional paid dispatch is not connected. The Supervisor has separate deployment configuration and metered receipts. Operators configure available profile identity, provider, model, harness, effort, repository scope, concurrency and budgets. They cannot create role kinds or change lifecycle topology.

Automation policy is versioned and audited. It controls enrollment, repositories, task and Team spending, reviewer actors, checks, approval semantics, and automatic merge. Stopping a Team revokes active leases and pauses work without erasing usage. Enabling it again does not silently resume paused tasks.

## Developer runtime

The harness owns source discovery, reads and edits, tools, model conversation, provider session state, compaction, and usage receipts. The platform owns lifecycle, workspace, cost admission, container policy, validation, Git operations, authorization, and audit.

The provider-neutral adapter exposes supported start, resume, interrupt, compact, inspect, and seal operations through capability flags. Unsupported provider behavior is explicit rather than simulated.

A `DeveloperSession` records task, profile, harness, provider, model, native identifier, workspace/state locations, requirement revision, current revision, checkpoint, and timestamps. Fresh review repairs receive the original objective, current source/diff and exact feedback rather than replaying the implementation transcript. Required missing state blocks execution; the system never invents continuity.

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

Commit and PR titles use short English Conventional Commit subjects. PR descriptions
include the implementation summary, changed-file evidence, validation revision/checks
and review requirements. Updating an existing PR refreshes its title and description.

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
- `supervisor/infrastructure`: bounded task decisions, provider wire schemas, and durable-memory adapters; recovery uses the shared engineering lease guard rather than depending on the Supervisor service;
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

Settings owns language (English/Georgian), light/dark theme, Default/Jarvis display mode, and accent controls. These browser-local preferences save immediately; the sidebar footer carries `© Nikolla_L`. Accent selection supports six presets, a native keyboard/touch hue slider, and an optional cycle through the presets every eight seconds. Cycling uses one shell-owned timer, pauses in hidden tabs or reduced-motion mode, and stops on manual color selection. It makes no backend or model calls. Solid accent buttons choose a contrasting foreground; primary gradients soften their secondary stop when necessary to keep labels readable in either theme without changing decorative colors.

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

## Jarvis: ambient operations companion

Jarvis is the default display name of the optional read-only operations companion in the application shell. Settings → Jarvis assistant → Assistant name lets the operator save another name (1–40 characters). The deployment-wide name is stored in the existing companion preferences, survives restarts, and updates the launcher, panel, conversation labels and Settings heading across same-browser tabs. Renaming while disabled does not enable the assistant. It is presentation metadata, never a model instruction, Team role or Developer session setting. Technical Observer module names, APIs, event names and stored history remain stable for integrations.

The companion combines deterministic attention rules, bounded product queries, saved conversations and a small animated particle halo. It is not an engineering role, does not buy provider calls and cannot issue engineering commands. Its failures do not change task execution, Team budgets, native sessions, validation or merge gates.

### Ownership and extraction boundary

`backend/app/observability/observer/domain.py` owns pure attention, routing and capacity policies. `application.py` composes use cases against `ports.py`: `ObserverReads`, `ObserverStore` and `LocalObserverModel`. The SQL read adapter, Observer persistence, Ollama adapter and instrumentation implement these ports. Only bootstrap wires them to existing analytics and observability queries. HTTP routes live in `interfaces/http/routes/observer.py`; frontend code is isolated in `frontend/src/lib/observer`. The shared layout and Settings page each compose a single Observer component.

The domain and application do not import execution implementations. No delivery command, model provider credential, Docker client, shell runner, workspace or Developer transcript is available through the Observer contracts. Existing SQL facts are read in read-only transactions with short statement timeouts. An independent single-connection pool bounds Observer persistence/query contention; this connects to the same application database, not a second database. Query adapters can later be replaced with HTTP read clients without changing the use cases or UI contract.

Observer owns `observer_events`, `observer_conversations`, `observer_messages`, `observer_questions`, `observer_preferences` and `observer_model_runs`. These tables do not create foreign-key dependencies on execution records. Their only relational links are within Observer. Browser-isolated conversation identifiers are scoped to the original task/Team/dashboard and cannot be reused across scopes. Production operator authentication still belongs to the existing protected ingress; the HttpOnly same-site browser cookie separates histories, but is not a replacement for authentication or a multi-tenant authorization model.

### Facts and attention

The initial rules cover sustained host CPU/RAM/disk pressure, task-budget pressure, unknown stopped billing, consecutive validation failures, repeated no-progress reports, human attention and recorded infrastructure incidents. Utilization must remain observed above its threshold for five minutes. Monitoring gaps break that continuity and do not count as downtime or recovery. A truncated task cohort cannot resolve events for omitted tasks.

Attention items are fingerprinted, deduplicated and retain measured facts, source, timestamps and rule revision. Repeated old container incidents are grouped by service/condition. When a current container is running or pressure measurements have recovered, an unclosed historical incident is labeled as a record needing reconciliation rather than presented as a newly confirmed outage. This does not alter the original incident or claim that container state proves endpoint readiness. Operators can acknowledge items or snooze them; severity escalation can bring them back to attention. Briefings are deterministic and never invoke a model on page refresh. Notification preferences include normal, warnings-only, critical-only and silent. Conversation entry offers a bounded “since my visit” view; the operator explicitly advances the seen marker.

The query registry routes to bounded groups: attention, tasks, AI usage, resources, incidents, recent changes, forecasts and product knowledge. Task detail follows the current page automatically. Task/team UUIDs are validated; the frontend supplies references, never arbitrary SQL, PromQL, tool definitions or measured values. `askObserver(question, context)` is the frontend integration seam for future chart/card actions. New capabilities should extend the read port and registry, not add a generic agent loop.

AI usage comes from durable receipts; resource facts come from the existing Prometheus query adapter. Answers show source/freshness chips and explicit missing-data statements. Task counts and detailed rows have separate completeness semantics; detail is capped at 100 recent/active tasks. No raw logs, descriptions, diffs or source code are included. Model/profile names and user text remain untrusted and are rendered as text, never HTML.

### Optional local AI, never paid fallback

Settings → Jarvis assistant controls local AI, the installed model, free-memory reserve, output-token ceiling and response timeout. Changes persist in the existing companion preferences and take effect across API/controller processes without a restart. Local AI starts disabled unless the operator enables it. Settings can inspect private Ollama, explicitly download an allowlisted local Qwen model, and run a local-chat test. No chat, page refresh or toggle automatically downloads weights. Downloads require idle engineering and verified disk headroom; the operator may cancel them. Installed model choices can be refreshed without loading weights. The private Ollama service has no published port; outbound connectivity permits model downloads, while `OLLAMA_NO_CLOUD=1` and adapter checks reject cloud inference. No provider credentials or paid fallback exist in this path.

The local model writes a natural-language explanation from at most six compact facts and two short recent messages. Stable facts precede variable conversation text for prefix reuse; timestamps/source metadata stay outside model context but remain visible as evidence chips. Replies use a strict answer/fact-ID schema; malformed answers and invalid references fall back to facts. Missing-source notices cannot be suppressed. Inputs remain untrusted and there are no write tools, SQL, shell or source access. The prompt has a 12 KB hard ceiling, context is 4096 tokens, and output is configurable at 128–768 tokens. Thinking is disabled. Reference validation does not guarantee factual prose: capacity questions and their short follow-ups bypass the model entirely. Their deterministic policy never approves another runner from low CPU alone and recommends against starting work under disk/RAM pressure. See the official [Ollama chat API](https://docs.ollama.com/api/chat).

Local AI admission fails closed on missing/stale memory, insufficient headroom, CPU pressure, unresolved OOM or queued/running engineering work. Cold weights are budgeted separately; already-resident weights are not counted twice, with additional context headroom retained. Inference uses two CPU threads and at most one question at a time. A recently used model stays warm for up to 60 seconds; no model is loaded by status polling. While warm, a two-second guard releases Jarvis's model under execution/resource pressure. The master switch cancels requests and explicitly unloads its model. An Interpreter-shared model uses zero keep-alive and is never unloaded out from under active Interpreter work. An unavailable Ollama may prevent immediate release; its finite keep-alive is the fallback. Briefings never invoke AI. Jarvis receipts remain separate from Developer usage/budgets. These controls bound interference but cannot guarantee zero CPU/RAM overhead or race-free hardware reservation.

Local browser verification on September 9, 2026 measured a 16.7-second cold reply and a 5.6-second warm follow-up on the installed CPU-only model; these are smoke measurements, not latency guarantees. Outside-click and explicit Close preserved the ongoing reply and conversation, with an unread badge and reply notice. Switching off after a reply and during inference both left the model unloaded. No paid inference was used for these checks.

Configuration:

```dotenv
OBSERVER_ENABLED=true
OBSERVER_LOCAL_AI_ENABLED=false
OBSERVER_MODEL=qwen3.5:4b
OBSERVER_MIN_AVAILABLE_MEMORY_MB=1024
OBSERVER_PROACTIVE_COOLDOWN_SECONDS=900
```

These environment values seed the deployment defaults; saved Settings take precedence for the local-AI policy. The memory value now means memory to leave free after estimated model use, not a hard container allocation. The initial reserve is 1024 MiB; Settings enforces at least 512 MiB. Model footprint is an estimate from installed weight size plus context/runtime headroom and does not replace Docker memory limits. The master switch remains independent of the local-AI toggle, and a model/policy change cancels current Jarvis requests before applying the new policy.

### Master switch and shutdown behavior

Settings → Jarvis assistant (or its chosen name) has a persisted master on/off switch. Turning it off stops the controller's detection task, cancels active Observer question/inference tasks, rejects new Observer work, clears its cached projections and removes frontend polling, animation and panel activity. Conversations are retained for re-enablement. Same-browser tabs receive the change through BroadcastChannel; other connected clients discover the switch on their next bounded status request and then stop polling.

Re-enablement is push-driven using PostgreSQL LISTEN/NOTIFY. The disabled feature has no recurring detection or model timer. One idle configuration-listener connection per API/controller process remains so the Settings switch can wake it; loaded application code and stored records are not physically removed. Setting `OBSERVER_ENABLED=false` at deployment and restarting also removes that listener. Shared Ollama, Interpreter, Prometheus and Team workflows are not stopped by an Observer switch. In-flight local responses are cancelled and unknown interrupted usage remains unknown, never fabricated as zero.

Shutdown cancels the stream task, not both its ASGI parent and child. Short in-flight read requests may drain; interrupted-question accounting has a shielded three-second cleanup bound so disconnects do not strand the companion's database connection. This cleanup cannot restart inference or mutate engineering records.

Configuration application is serialized within each process; preference writes and cross-process notifications commit together. Crash recovery marks stale unfinished local receipts interrupted without inventing missing token counts. Inference bypasses cached model readiness, checks engineering activity immediately before starting, and enforces a wall-clock response deadline even if upstream output trickles continuously. Malformed model inventories fail closed; unsupported non-chat models are not admitted.

Local Docker smoke evidence (September 9, 2026): Settings persisted local AI with `qwen3.5:2b`, a 1024 MiB reserve, 256 output-token ceiling and 60-second timeout. A real grounded reply completed in approximately 27 seconds on CPU-only Ollama, reporting 528 prompt tokens and 123 output tokens. Switching the master off during a subsequent request cancelled the upstream request, recorded interrupted usage as unknown, left no model loaded in Ollama, and rejected new questions. Re-enabling preserved configuration. Engineering AI receipt counts, token totals, costs and reservations were identical before and after these checks. This is functional smoke evidence, not the 50-question quality benchmark or a proof of zero performance overhead.

### UI, transport, retention and metrics

Outside click, Escape and Close hide the popup without cancelling its pending answer or clearing the conversation. A reply arriving while hidden displays a brief notice (unless muted) and an unread badge; reopening shows the same thread. New chat, navigation and the master switch still cancel obsolete work. Failed or cancelled requests have an explicit message, never an empty placeholder or automatic model retry.

The Observer follows the application's shared Default/Jarvis display setting and light/dark/accent tokens. Default uses a quiet ring and rounded panel; Jarvis adds a particle core, neon framing, a subtle header grid and matching control-center typography inside the panel and notice bubble. The isolated Canvas2D renderer caps animation at 24 frames/second while responding, 15 idle in Jarvis and 12 idle in Default. There are no animation network requests or model calls. Rendering pauses in hidden tabs, honors reduced motion and has an inline SVG fallback. Application state drives color/motion; animation cannot change application state.

The launcher and panel header support mouse, touch and pen dragging. Both move the same browser-local anchor; the chat panel and notice bubble choose an adjacent on-screen placement, including after viewport resize or mobile keyboard changes. Position is saved as relative coordinates in local storage when a drag ends, never in task state or a backend request. Focused drag controls also support arrow keys (Shift for larger steps), Home and a reset-position button. A drag does not accidentally open or close chat. The floating non-modal dialog leaves the app usable, closes on outside click or Escape, and retains a scrollable conversation and composer in compact viewports. Turning Observer off removes the drag controls, panel and renderers. Attention collapses during conversation so it cannot obscure answers.

Canonical APIs are under `/api/observer`: configuration, status, briefing, events, conversations, usage, questions and question SSE. Question SSE carries read-tool status and validated answers. Hiding the popup keeps its existing stream connected; disconnecting the page cancels it. Persisted claims prevent duplicate inference, with one global active answer, twelve admitted questions per minute and finite deadlines. There is no detached model loop or automatic retry.

Local model receipts are separate from paid `ai_runs` and never enter Team spending. They store reported token counts/durations or unknown values, including interrupted work. Low-cardinality `observer_*` counters/histograms cover questions, briefings, tools, local requests/failures/tokens, capacity denial, deterministic fallback and durations. Conversation history is retained for thirty days; resolved attention history for ninety days. No private thinking is persisted. The deployment switch stops periodic cleanup along with the other Observer work; cleanup resumes when enabled.

### Acceptance boundary

Focused checks cover capacity/missing-data behavior, read-only routing, input/scope bounds, invented fact rejection, deterministic briefings, master-switch cancellation, PostgreSQL hold/dedupe/snooze/resolution, conversation isolation and migration metadata. Browser checks exercise grounded chat/SSE, saved history, desktop/mobile layouts and disabled-state polling. No paid model task is needed for these checks.

Production acceptance remains separate: complete the engineering and monitoring gates, benchmark at least fifty representative local-model questions, measure shared-host interference and animation performance, and tune notification noise during dogfood. Broader statistical anomaly families, richer natural-language synthesis, automatic daily briefings and voice are not claimed as accepted by these initial checks. There is no voice/microphone access, model fine-tuning, new agent role or mandatory external animation runtime.

## Backend maintenance history

The backend review covers domain/application boundaries, leased execution and cancellation, spending admission/receipts, context-governor and checkpoint contracts, delivery gates, integration adapters, monitoring, analytics and migrations. Safe corrections remove writes/row locks from assistant preference reads, use the matching resource threshold when deciding whether an incident recovered, reject empty or non-finite-timestamp monitoring series, and exclude future-dated receipts from current-window cost charts. No Developer prompt, harness policy, token threshold, reservation or merge rule is changed by this cleanup. Companion domain/application imports now have an explicit architecture guard as well.

Historical migration and local regression checks are not evidence that the currently running containers include subsequent source edits. Rebuild affected backend/controller and runner images before evaluating changes; starting existing images alone does not deploy new code. Database, Docker and live-provider checks have separate prerequisites.

Two existing deployment/upgrade cautions remain outside automatic cleanup: the local PostgreSQL `template1` database reports collation 2.36 against runtime 2.41 (the application database itself reports matching 2.41); and the historical canonical-identifiers migration rewrites stored version-prefixed task branch names without renaming external Git refs. Existing migration history and live Git branches are not rewritten during this review. Older deployments crossing that historical migration must reconcile published branch identities with GitHub before resuming delivery; template maintenance requires a deliberate database administration step, not an application reset.

## Final operating rule

This MVP has no product-edition naming scheme. Dependency pins, provider API paths,
signed webhook formats, database revisions, prompt/cache identities and optimistic
concurrency counters remain technical compatibility and audit mechanisms.

Patch localization, application and exhausted repair failures can still require human
attention. Explicit resume can recover a saved rejected patch only under its source-hash
and attempt guards, without another paid request. Lower spending on a failed task is
not successful automation; measure token usage and delivery success together.

The checkout remembers code. PostgreSQL remembers authoritative state, policy, accounting, evidence, and continuity. A bounded checkpoint remembers unresolved intent. Native context carries only the current slice. Models implement and reason; deterministic code retains authorization, spending, validation, publication, and merge authority.
