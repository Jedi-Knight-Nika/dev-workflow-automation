# Autonomous Engineering Worker

## Product and architecture reference

**Status:** MVP under active development  
**Audience:** product, engineering, operations, and future contributors  
**Primary mode:** one trusted operator, local or single-server deployment  
**Core rule:** AI performs bounded semantic work; deterministic software owns authority, state,
routing, budgets, retries, external side effects, and recovery.

This document is the canonical description of the product as it exists. Operational commands live
in `DEVELOPMENT.md`; migration and test conventions remain beside their respective subsystems.

## 1. What the product does

Autonomous Engineering Worker is a control center for AI-assisted software delivery. It receives a
task manually or from a task-management integration, associates it with a Team and repository,
creates durable Jobs for specialized AI Agents, validates their structured results, routes those
results through a configurable workflow, and prepares a pull request for human-controlled delivery.

The product is designed to automate the repetitive parts of engineering work without turning AI
models into system administrators. Models can investigate, plan, edit code, interpret failures, and
review changes. The platform decides whether a tool is permitted, which Agent runs next, when a
retry is allowed, when evidence is stale, and when a human must intervene.

The normal lifecycle is:

```text
Task source or manual task
        -> deterministic intake and profiling
        -> Thinker (when planning is required)
        -> Executor
        -> deterministic validation / Tester
        -> Reviewer
        -> deterministic delivery
        -> GitHub pull request and external review
        -> merge gate
        -> ready for testing
```

The sequence is a default, not hardcoded product law. Team workflows are directed graphs whose
outcome edges control the actual next Job.

## 2. Product boundaries

The product owns:

- durable Tasks, Jobs, results, events, findings, checkpoints, incidents, and usage records;
- Teams, Roles, Agents, workflow graphs, runtime defaults, and execution policies;
- repository discovery, local caches, task worktrees, and repository knowledge;
- AI-provider request construction and structured-result validation;
- GitHub delivery and review evidence;
- Linear and Trello task ingestion;
- approval, notification, resilience, and recovery behavior.

External systems remain authoritative for their own concerns:

- GitHub owns remote repositories, pull requests, checks, reviews, and merge state;
- Linear and Trello own the source task records;
- AI providers own model availability and usage metering;
- PostgreSQL is authoritative for orchestrator state;
- Git worktrees are authoritative for in-progress code content.

## 3. Core domain model

### Role

A Role is a reusable worker template. It defines the type of engineering work, system instructions,
capabilities, permissions, allowed result types, knowledge defaults, normalized AI runtime defaults,
and which settings an Agent may override.

Built-in templates use the same schema as custom Roles and can be cloned. Runtime behavior never
depends on a Role display name.

Built-in worker Roles are:

- **Thinker** — analyzes requirements, repository context, risks, and architecture; produces or
  revises an implementation plan.
- **Executor** — edits the task worktree, runs development checks, and produces an implementation.
- **Tester** — evaluates deterministic validation evidence and performs task-specific verification.
- **Reviewer** — independently reviews correctness, architecture, regressions, and missing cases.
- **Deliverer** — represented as a workflow responsibility; delivery side effects remain
  deterministic platform operations.

Intake normalizes external events. Orchestrator is a system control node, not an unconstrained AI
employee.

### Agent

An Agent is a concrete configured worker assigned to a Role and Team. It selects a provider/model,
adds Agent-specific instructions, and stores only explicit runtime, permission, or knowledge
overrides. Values not overridden continue to inherit from the Role.

Agent runtime resolution follows:

```text
platform constraints
  -> account defaults
  -> Team policy
  -> Role runtime defaults
  -> Agent explicit overrides
  -> task execution strategy tuning
  -> model capability validation
  -> provider adapter
```

Later layers cannot exceed earlier security or budget ceilings. Runtime tuning never grants extra
permissions.

### Team

A Team groups Agents, repositories, task sources, concurrency limits, execution policy, and one
versioned workflow graph. Teams can mix built-in and custom Roles. A task is pinned to a Team and a
workflow version so historical routing remains explainable after later edits.

### Workflow

A workflow is a directed graph:

- nodes represent Agents or deterministic system destinations;
- edges match typed Agent outcomes;
- an edge may specify the next Job type, internal Task state, external semantic status, priority,
  and guard configuration;
- cycles are valid but bounded by review, test, replan, retry, cost, and no-progress policies;
- unmatched or ambiguous outcomes fail safely rather than disappearing.

Every routing decision is persisted with the source node, result, matched edge, target, workflow
version, and resulting state.

### Task

A Task is the durable unit of engineering work. It contains requirements, repository and Team
assignment, current state, external identity, branch/workspace information, pull-request metadata,
task profile, execution strategy, workflow version, and lifecycle timestamps.

Tasks can be paused, resumed, taken over manually, cancelled, and archived. Archival preserves the
execution history; terminal tasks are not casually hard-deleted.

### Job

A Job is one bounded execution by one Role/Agent. Each normal transition creates a fresh Job and a
fresh AI session. Job state includes queueing, claim/lease ownership, execution, retry delay,
resource/configuration/human waits, success, failure, timeout, and cancellation.

Persistent context crosses Job boundaries through Task Memory, Agent checkpoints, findings,
repository state, and artifacts—not through an endlessly growing model conversation.

## 4. Runtime architecture

The local Compose topology contains:

- **PostgreSQL with pgvector** for durable state and repository embeddings;
- **FastAPI backend** for the control-plane API, webhook ingestion, and notification delivery;
- **scheduler/worker process** for reconciliation, job claiming, execution, indexing, delivery, and
  recovery;
- **SvelteKit frontend** for operator workflows.

Production adds Caddy as the only public ingress and uses constrained disposable Docker containers
for Agent Jobs. The API does not receive the Docker socket. The scheduler is trusted infrastructure
because Docker control is host-level authority.

The backend follows an inward dependency rule:

```text
API and worker entrypoints -> application use cases -> domain policies
                                  ^
                                  |
                    infrastructure implements ports
```

- `backend/app/domain` contains framework-free policies, entities, and value objects.
- `backend/app/application` coordinates use cases through Protocol ports.
- `backend/app/infrastructure` implements persistence, Git, provider, integration, worker, and
  operating-system adapters.
- `backend/app/api` translates HTTP/WebSocket input and output.
- `backend/app/bootstrap` composes concrete dependencies.
- `backend/app/db/models` groups SQLAlchemy records by domain while preserving one registry import.
- `frontend/src/routes` owns pages; `frontend/src/lib` owns reusable components, services, state,
  and shared types.

## 5. Task ingestion

Tasks can be created manually through the UI/API or imported from configured task sources.

### Linear

Linear supports signed webhook ingestion, polling/reconciliation, cursor-based pagination, member
and workflow-state discovery, semantic status mapping, and deferred synchronization when Linear is
temporarily unavailable. Internal state remains authoritative while external synchronization waits.

### Trello

Trello supports credential validation, board/list discovery, configured source lists, a default
repository, polling-based task ingestion, cursor-safe traversal where applicable, and manual Sync
Now. Current Trello scope is inbound task ingestion; broad outbound workflow mapping is deferred.

Webhook deliveries are deduplicated and processed durably. External payloads are treated as
untrusted input.

## 6. Adaptive execution

A deterministic TaskProfiler classifies independent dimensions:

- complexity;
- risk;
- parallelizability;
- uncertainty;
- tool density.

The ExecutionStrategyResolver selects bounded settings such as model turns, tool calls, replans,
test/review cycles, human gates, and whether parallel investigation is allowed.

Current strategy families are:

- **FAST** — bounded implementation with cheaper validation for low-risk, clear work;
- **STANDARD** — normal plan/build/test/review flow;
- **HIGH_ASSURANCE** — stronger reasoning and gates for broad or risky work;
- **PARALLEL_INVESTIGATION** — allows bounded read-oriented specialization while retaining a single
  writer.

The graph remains the routing authority. Adaptive strategy changes resources and gates within that
graph; it does not create a second orchestrator.

## 7. AI runtime configuration

Roles store provider-neutral runtime profiles including:

- preferred provider/model;
- reasoning default and allowed range;
- maximum output tokens;
- optional temperature where supported;
- context strategy (`MINIMAL`, `BALANCED`, or `DEEP`);
- model turns and tool-call limits;
- Job timeout and attempts;
- structured-output requirement;
- override policy.

Agents store sparse overrides. Changing a Role automatically affects inheriting Agents; explicit
Agent overrides survive while still permitted. Provider/model changes revalidate overrides, and
incompatible active configurations are rejected before a worker launches.

A versioned capability registry describes supported reasoning levels, sampling controls, output
limits, tools, structured output, and parallel tool calls. Unknown models receive conservative
defaults. Provider adapters translate normalized settings into OpenAI, Anthropic, or Google request
fields and omit unsupported optional parameters.

Before model execution, the worker captures an immutable effective-runtime snapshot. Each WorkerRun
records the Role version, Agent configuration version, capability version, strategy version,
sanitized runtime configuration, and SHA-256 configuration hash. Secrets are never included.

## 8. Context, memory, and knowledge

Every Agent Job normally starts with a fresh provider session. ContextCompiler reconstructs a
focused briefing from:

- task description and acceptance context;
- current plan and Task Memory;
- prior checkpoint and relevant result;
- unresolved review/test findings;
- repository map and current Git state;
- SHA/diff delta since the previous checkpoint;
- targeted Role/repository knowledge retrieval.

The Executor receives full repository context only when needed initially and delta-oriented context
thereafter. Large logs and command output are bounded. Current repository/worktree state outranks
stale AI summaries.

Repository indexing excludes generated, binary, dependency, build, and other low-value content.
Content hashes deduplicate chunks and embeddings. Repository knowledge tracks indexed revision and
can be queued, updated, failed, or stale independently from Git code access.

## 9. Worker and tool execution

Workers execute one Job with a lease token. Claims use PostgreSQL locking and Team-scoped advisory
coordination to respect concurrency limits. The scheduler supports bounded concurrent Jobs while
shared repository cache/worktree operations use repository-scoped locks.

The Tool Gateway is the authority for file, command, Git, and network operations. Effective access
is resolved from platform, Team, Role, Agent, Job, and sandbox constraints. Agents cannot grant
permissions to themselves or each other.

Important safeguards include:

- canonical workspace-path and symlink containment;
- separate create/write/delete permissions;
- command inspection including commands nested in shell/interpreter arguments;
- hard denial of privilege escalation, Docker socket access, and host escape;
- command timeout, output size, process, memory, CPU, and tool-call limits;
- approval argument hashing to prevent approve-then-change behavior;
- audit events for authorization decisions and tool execution;
- process-tree termination with a bounded post-kill drain.

Only one writer should mutate a task worktree at a time. Read-only analysis may be parallelized only
when the strategy and infrastructure permit it.

## 10. Validation and review

Correctness is evidence-driven. The system can capture lint, type-check, unit/integration test,
build, CI, pull-request review, and acceptance evidence. Validation results are bound to the exact
repository revision and validation configuration; a new commit invalidates old readiness.

The Tester fast path can accept successful deterministic checks for eligible low-risk work without
spending an AI call. An AI Tester handles ambiguous results, task-specific validation, failure
classification, and coverage gaps.

Reviewer outcomes distinguish:

- pass;
- actionable implementation failure, routed to Executor;
- architectural failure, routed to Thinker;
- uncertainty or human need.

Repeated finding fingerprints and repeated unchanged repository/test state trigger no-progress
protection instead of unbounded rework.

## 11. GitHub delivery

Repositories are preferably discovered through a GitHub App installation. The platform maintains a
shared repository cache and isolated task worktrees, sanitizes branch names, uses argument-list Git
commands, and keeps tokens out of clone URLs and logs.

Delivery is deterministic:

1. verify the task and evidence state;
2. create commits according to policy;
3. push the task branch;
4. find or create the pull request idempotently;
5. persist the PR number immediately;
6. synchronize external task status;
7. wait without keeping an AI worker alive.

Merge gates can require current CI, Tester/Reviewer evidence, no blocking findings, no conflicts,
and external reviews. Agents do not merge directly. After merge, the platform updates repository
knowledge and external semantic state.

## 12. Resilience and recovery

Failure handling uses typed classes and the smallest affected scope. A provider request failure is
not automatically a failed Task, and one blocked Team does not stop unrelated work.

Failures distinguish provider outage/rate limit/authentication/model configuration, integration
failure, worker crash/timeout/OOM, protocol failure, tool failure, policy denial, engineering
failure, no progress, security incident, external wait, and database failure.

Recovery behavior includes:

- bounded retry with exponential backoff for transient failures;
- separate provider, integration, worker, protocol, and engineering retry counters;
- persisted health and circuit-breaker state;
- waiting Job states that release workers;
- gradual requeue after resource recovery;
- durable-result recovery when a worker completed before the scheduler committed completion;
- stable incident fingerprints and notification deduplication;
- idempotency/find-before-create for retryable external side effects.

Provider authentication, unavailable models, and invalid runtime settings enter
`WAITING_CONFIGURATION` and raise an actionable incident without retry storms. Engineering test or
review failures remain ordinary workflow outcomes until budgets or progress rules are exhausted.

PostgreSQL is authoritative. When it is unavailable, authoritative transitions and irreversible
actions must stop rather than continue from guessed state.

## 13. Budgets and cost control

WorkerRun records input/output tokens, duration, provider request identity, model, and estimated
cost. Limits can be enforced at Job, Task, Team, and account/month scope. A hard stop allows the
current safe boundary to finish, blocks new AI work, and creates an actionable condition.

Infrastructure retry counters do not consume engineering rework budgets. Runtime limits are
enforced by software, not model instructions. Zero or unavailable pricing is treated as unknown,
not as proof that execution is free.

## 14. Settings and policy

Global Settings contains account-level defaults and platform behavior, not Team/Role/Agent details.
Current sections cover general preferences, AI defaults, execution, safety, notifications,
knowledge, retention, and security-facing behavior.

Configuration precedence is restrictive for security:

```text
platform hard policy -> account defaults -> Team -> Role -> Agent -> Job restriction
```

Platform-locked rules cannot be weakened. Settings changes increment a version and operational or
security-relevant changes are audited. Team overrides inherit rather than copying global defaults.

## 15. Notifications, incidents, and approvals

Notifications support in-app delivery and Telegram. Default intent is:

- informational and recoverable warnings: in-app;
- action required and critical: in-app plus Telegram.

Incidents represent persistent root causes with occurrence counts and affected entities. Repeated
events update one incident instead of spamming the operator. Acknowledged means seen; resolved means
the condition no longer blocks or threatens the system. Recoverable resource incidents can resolve
automatically.

Approval requests are durable and concurrency-safe. Approval grants one exact hashed action, not a
broad permission increase. Expired or denied approvals do not silently execute.

## 16. Repository management

The Repositories area answers which codebases Agents may use. It separates:

- **Code access** — discovery, clone/cache/fetch availability;
- **AI knowledge** — indexing, indexed revision, chunks, and freshness.

Repositories show Team/Task/workspace/task-source dependencies. Batch GitHub import is supported.
Lifecycle actions include enable/disable, archive/restore, knowledge update, and dependency-aware
permanent removal. Active workspaces are never removed by retention cleanup.

Repository caches and completed/archived task workspaces follow configured retention. Cleanup is
audited and repository-scoped locking prevents concurrent Git cache corruption.

## 17. Integration management

Integrations and Repositories remain separate domains with cross-links:

- Integrations owns credentials, connection identity, health, sync, webhooks, provider-specific
  configuration, and dependency visibility.
- Repositories owns codebase lifecycle, cache/worktree state, indexing, usage, and repository
  settings.

Integration groups are source control, task management, AI providers, and package registries.
Credentials are encrypted at rest and write-only through the API. Cards expose user-facing status,
identity, usage, and next action; technical diagnostics remain progressively disclosed.

Supported integrations include GitHub, Linear, Trello, OpenAI, Anthropic, Google, npm registry, and
PyPI registry.

## 18. User interface

Primary navigation is:

```text
Dashboard
Tasks

Workforce
  Teams
  Agents
  Roles

Resources
  Repositories
  Integrations

System
  Notifications / incidents
  Settings
```

The Dashboard summarizes throughput, active work, usage/cost, Teams, workers, incidents, and system
health. Task pages expose lifecycle controls, Jobs, events, validations, findings, memory/context,
repository/PR state, and terminal access. Roles open into detailed views including capabilities,
permissions, result contracts, runtime defaults, and active/inactive Agent counts.

Team workflow editing uses a visual canvas backed by the same versioned graph that execution reads.
Resource pages use compact list states and detail drawers so routine status remains readable while
advanced diagnostics stay available.

## 19. Terminal sessions and manual takeover

A task can enter manual takeover, cancelling queued autonomous work while preserving the workspace.
Terminal sessions issue time-limited access tokens, audit ordered input/output metadata, and close
the underlying PTY process when the session ends.

Terminal runtime ownership is persisted to prevent reconnecting through the wrong backend process.
The current product is optimized for a single application replica; multi-replica terminal routing
requires sticky/owner-aware WebSocket routing or an external terminal runtime.

## 20. Data and audit model

SQLAlchemy models are split by domain: Agents/Roles, Teams, Tasks/Jobs, workflows, integrations,
execution, notifications, resilience, settings, and terminals. Alembic migrations form immutable,
linear deployment history.

Important durable records include:

- Tasks, Jobs, TaskEvents, assignments, and workflow transitions;
- workflow definitions, nodes, edges, and version snapshots;
- WorkerRuns and effective runtime provenance;
- validation records and review findings;
- Task Memory, checkpoints, and context metadata;
- tool events, approvals, terminal sessions/events;
- integrations, webhook deliveries, and pending synchronization;
- incidents, notifications, health state, failure events, and retry state;
- account settings and settings audit events.

Foreign-key and hot-path indexes support polling, claiming, routing, and history queries. Append-only
operational data requires a deliberate retention/archival policy as deployment volume grows.

## 21. API surface

The FastAPI service exposes OpenAPI documentation at `/docs`. Major API families are:

- `/health` — liveness and readiness;
- `/api/v1/dashboard` and `/api/v1/activity` — operational summaries;
- `/api/v1/tasks` — task lifecycle, Jobs, events, validation, findings, PR, merge, and sync;
- `/api/v1/teams` — Teams, assignments, workflows, and model validation;
- `/api/v1/roles`, `/api/v1/agents`, `/api/v1/agent-runtime`, `/api/v1/ai` — workforce and runtime;
- `/api/v1/repositories`, `/api/v1/integrations`, `/api/v1/github`, `/api/v1/linear`, and
  `/api/v1/trello` — external resources;
- `/api/v1/settings` and `/api/v1/execution-policy` — defaults and authority;
- `/api/v1/notifications`, `/api/v1/incidents`, and `/api/v1/resilience` — attention and recovery;
- `/api/v1/tasks/{id}/memory` and related context endpoints — durable Agent context;
- `/api/v1/terminal` and task terminal endpoints — manual terminal access;
- `/webhooks/github`, `/webhooks/linear`, and Telegram webhook routes — signed external events;
- `/events/stream` — server-sent operational updates.

Large list/read models are aggregated server-side to avoid frontend N+1 request patterns. Secrets
are never returned.

## 22. Security model

The MVP assumes a trusted single operator and trusted network boundary. Platform API authentication,
multi-user authorization, and tenant isolation are intentionally not implemented; the service must
not be exposed publicly without an authentication boundary.

Implemented controls include encrypted stored credentials, webhook signatures, least-privilege
worker database provisioning, sandbox and Tool Gateway enforcement, secret redaction, production
secret validation, restricted containers, scoped workspaces, branch protection guidance, and
auditable approvals/actions.

The application encryption key protects all stored integration credentials. Back up before rotation,
stop writers, use the transactional rotation command, update deployment configuration, and restart.
If any private key or `.env` content is shared, rotate it; Git ignore is not a security boundary.

## 23. Deployment and operations

Local development uses `compose.yaml`. Production uses `deploy/compose.production.yaml` with Caddy,
private service ports, required strong secrets, health ordering, restart policies, restricted worker
credentials, and persistent database/workspace volumes.

Operational capabilities include:

- Alembic migration on startup;
- readiness checks;
- worker registration and heartbeats;
- startup reconciliation;
- PostgreSQL/workspace backups with checksums and retention;
- guarded destructive restore;
- transactional credential-key rotation;
- archived-workspace cleanup;
- real-workflow validation against configured integrations.

Exact commands and safety procedures are maintained in `DEVELOPMENT.md`.

## 24. Testing and quality

Backend tests are organized by domain, application, infrastructure, API, integration, and
architecture boundaries. PostgreSQL integration tests cover database-specific concurrency and
routing behavior. Architecture fitness tests enforce dependency direction.

Frontend checks include ESLint, Prettier, TypeScript/Svelte diagnostics, unit tests, production
build, and a Playwright end-to-end specification. Lockfiles and frozen installation commands make
builds reproducible.

The standard complete check is:

```bash
make check
```

Database integration tests are opt-in because they require PostgreSQL; see
`backend/tests/README.md`.

## 25. Current product decisions and limitations

These are deliberate boundaries, not hidden promises:

- no platform API authentication or multi-user/tenant isolation yet;
- no arbitrary provider SDK keyword arguments;
- no uncontrolled Agent-to-Agent chat or delegation;
- no multiple writers in one task worktree;
- no automatic merge based only on an LLM pass;
- no silent provider/model fallback unless explicitly configured and compatible;
- no long-lived AI worker while waiting for a provider, integration, human, or external review;
- no full transcript replay as default memory;
- no production-scale multi-replica terminal runtime yet;
- Trello primarily provides inbound task sourcing;
- parallel specialist fan-out remains bounded and is not the normal coding path.

## 26. Near-term priorities

Future work should be driven by observed production need. The most important expansion before public
or multi-user deployment is authentication, authorization, and Team/tenant isolation. Other likely
scale work includes externalized terminal routing, event-data retention/partitioning, richer eval
telemetry, provider fallback policy, and additional task/source-control adapters.

Avoid adding advanced controls merely because a provider exposes them. Preserve the product's core
shape: reusable Roles, concrete Agents, Team-owned workflows, fresh bounded Jobs, durable context,
evidence-based gates, and deterministic authority.

## 27. Architectural invariants

The system must never:

- allow an Agent to expand its own permissions or budget;
- route work through hidden direct Agent notifications;
- mutate task-manager state directly from model output;
- run an unbounded retry/rework/tool loop;
- treat a provider outage as an implementation failure;
- preserve Tester/Reviewer readiness after the repository revision changes;
- replay a non-idempotent external side effect blindly;
- silently drop an unmatched workflow outcome;
- inject unrestricted command output or an entire repository repeatedly into context;
- keep a worker alive during an external wait;
- merge solely because an AI says `PASS`;
- expose secrets in API responses, prompts, logs, snapshots, or incidents.

The enduring abstraction is:

```text
Role defines what an AI can do and how it normally runs.
Agent defines which concrete AI performs that Role.
Team defines who works together and under which policies.
Workflow defines where typed results go next.
Orchestrator executes those rules deterministically.
```
