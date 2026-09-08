# Product architecture and feature reference

## Purpose and operating model

Autonomous Engineering Worker is a single-operator control plane for AI-assisted software delivery. It accepts scoped work, runs a native coding session in a task-specific container, independently validates the result, publishes a pull request, processes review feedback and conditionally merges an approved revision.

PostgreSQL owns task state, admission, audit and cost records. Each task checkout owns its in-progress code. The native harness owns its conversation/tool history. GitHub owns remote checks, reviews and merge results. Those are separate sources of truth.

The [technical design](autonomous_engineering_worker_v2_technical_architecture.md) is the design input. This reference describes the implementation, not a claim that production acceptance has passed.

## Runtime sequence

1. Manual creation or an eligible signed/polled source event creates one ticket.
2. Deterministic routing chooses an allowed Team and repository.
3. Explicit enrollment records its profile, isolated storage locations and requirement version.
4. The controller fetches the current configured base branch and persists its SHA.
5. The Developer opens its Codex or Claude native session and edits/tests on demand.
6. An optional requested Thinker produces a bounded read-only plan.
7. A separate offline validator runs administrator-defined commands and creates the validated commit.
8. An optional read-only AI Reviewer can request corrections, but cannot authorize merge.
9. A credentialed Git-only publisher pushes the task branch and creates/reuses the matching PR.
10. Authorized, relevant feedback resumes the same Developer session with only the new feedback.
11. Current revision, validation, CI, reviewer authority, policy and mergeability are rechecked.
12. Conditional merge records completion; the tracker-status outbox synchronizes configured destinations.

Waiting for review, polling, status display and normal notes do not invoke an AI model.

## Backend ownership

The backend is a modular monolith. There is no second application-wide business-domain tree.

| Package under backend/app | Responsibility |
| --- | --- |
| intake | Source eligibility, signature verification, deduplication, event interpretation, tracker polling |
| engineering | Task lifecycle, leased phases, enrollment, execution, validation, controls, ticket queries |
| agent_runtime | Native session contracts, SDK/container adapters, normalized usage, reservations, compaction |
| delivery | Safe Git transfer, PR publication, current-SHA review evidence, conditional merge, status outbox |
| teams | Fixed role profiles, Team routing/scope, automation policy, shutdown, spending statistics |
| repositories | Repository metadata, discovery, scope/dependency checks |
| platform | Configuration, shared persistence setup, integration credentials, HTTP pooling, scheduling vocabulary, telemetry |
| interfaces/http | HTTP routes, request/response schemas and error translation |
| bootstrap | Adapter construction, dependency injection and scheduler composition |

Each business context owns the domain/application/infrastructure layers it actually needs. Domain contains business rules without FastAPI, SQLAlchemy, Docker or provider SDK dependencies. Application use cases depend on protocols and domain objects; adapters implement the protocols. A context does not receive empty directories just to satisfy a diagram.

HTTP entry points validate transport data and call use cases/ports. Bootstrap constructs adapters. Stateful cross-context coordination happens in infrastructure/composition, not through framework imports in the domain.

## Persisted entities

The initial schema contains 24 application tables:

- Configuration: account_settings, settings_audit_events, integrations.
- Teams: teams, team_agent_profiles, team_automation_policies, task_assignments.
- Repository inventory: repositories.
- Tickets: tasks, external_task_snapshots, task_repository_scopes, task_messages, task_events.
- Execution: jobs, task_phase_runs, developer_sessions, validation_runs, review_cycles.
- Metering: ai_runs, local_model_runs, pricing_catalog.
- Transport/operations: webhook_deliveries, external_status_syncs, worker_nodes.

There is one frozen initial schema and deterministic initial entities. Initial setup refuses a nonempty incompatible database. Changing a Python model cannot silently change the frozen SQL.

A Task has independent status, stage and wait reason, plus optimistic lifecycle and requirement versions. A Job is a leased deterministic execution unit; job success is not the same as successful feature delivery. AIRun is a native/cloud receipt, not necessarily one provider HTTP request.

### Status and phase

Statuses are NEW, ACTIVE, WAITING_EXTERNAL, WAITING_HUMAN, PAUSED, FAILED, CANCELLED and MERGED.

Stages are INTAKE, PLANNING, DEVELOPING, VALIDATING, PUBLISHING, REVIEWING, FIXING, MERGING and COMPLETE.

Suspension preserves the phase, checkout, native session and cumulative spending. A late result cannot advance a newer lifecycle version. Requirement changes are explicit, versioned and audited; stale approvals cannot authorize new code.

## Operator features

### Control center

- Current running workers, queue, active tasks and external/human waits.
- Team workload summaries, throughput, role usage and cost/time statistics.
- Native compaction and local interpreter statistics kept distinguishable.
- Infrastructure/host telemetry, integration health and recent operational events.
- SSE refresh with bounded polling fallback; no model calls for dashboard updates.
- Unknown cost/usage is shown as unknown rather than fabricated as zero.

### Tickets

- Board/list views, search, Team/source filters, sorting and repository metadata.
- Manual creation with requirements, priority, project, labels, due date and nullable relative story points.
- Blank estimates remain unestimated; numeric zero and fractions are preserved.
- Creation and Team assignment are free unless starting work is explicitly requested.
- Full task page with controls, source link, requirements and workspace/PR references.
- Append-only operator notes; explicit commands route deterministically.
- Status history includes from/to status and stage, actor and timestamp.
- Job history separates action, worker, attempts, timestamps and failure reason.
- Native-run receipts show role, model, cost, token/cache counts, timing and bounded result artifact.
- Validation evidence includes revision, exit status, timing and bounded output.
- Task usage CSV export includes task context and timestamp in its filename.
- Native session inspection and versioned model/harness changes while suspended.
- Pause, resume, cancel, archive and manual takeover preserve evidence and usage.

### Teams and profiles

- Team create/edit, enable/archive, repository scope, assignment and concurrency controls.
- Fixed INTERPRETER, DEVELOPER, THINKER and REVIEWER profiles.
- Configurable supported harness/model, effort, bounded additional instructions and explicit budgets.
- Thinker and Reviewer are optional and disabled by default.
- Versioned automation policy: enrollment, permitted repositories, task/Team spending, reviewer IDs, required checks and auto-merge.
- Stop work is a durable execution pause, not deactivation. It revokes live leases and pauses tickets.
- Enable execution reopens admission; paused tickets require explicit resume.
- Read-only lifecycle canvas with native browser fullscreen, exit control and browser Escape behavior.
- Queue, selected task details and milestone actor/timestamps remain inside fullscreen.

### Integrations and repository inventory

- GitHub App/PAT configuration and repository discovery/import.
- GitHub issue, PR/review/check webhook processing with actor and repository scope checks.
- Trello signed events plus authoritative card polling.
- Linear signed events plus eligibility-based polling.
- Slack signed Events API routing by workspace/channel/actor.
- Authenticated OpenAI, Anthropic and DeepSeek model discovery; availability is not inferred from a static list.
- Encrypted provider credentials; model keys only reach the relevant runner.
- Repository enable/archive/delete checks protect referenced work.
- Each new task fetches current source. Existing tasks retain their own branch and native history.

### Settings and presentation

Account settings contain general display preferences. Execution policy belongs to Teams; credentials belong to Integrations. Navigation supports theme and EN/KA resources. The fixed-workflow screens currently include English operational copy; complete Georgian parity is not claimed.

## Execution safety

The controller never runs project tests in its own process. Native coding, deterministic validation and credentialed Git transport use separate containers/security boundaries. Developer source access is limited to its task. Validation has no network/model/GitHub credentials. Helpers mount source read-only and use separate native homes.

The publisher transfers validated Git objects into a clean repository, disables hooks and uses fixed commands. Model text cannot select an arbitrary external write or turn itself into a merge approval. Auto-merge requires policy authorization and current authoritative GitHub evidence.

Production console routes are protected by operator HTTP authentication at the TLS proxy. Webhooks retain provider signature verification. This is a trusted single-operator product, not per-user RBAC or a hostile multi-tenant sandbox.

## Token efficiency

The default paid path is one Developer session. Source is read on demand through native tools, not repeatedly embedded into a custom planner/executor transcript. Failed native edits/tests can be corrected inside the same native run. Feedback sends a bounded delta to the persisted session. Deterministic events avoid interpretation; ambiguous text uses a small local model first when enabled.

Optional roles produce one bounded artifact. Repeated completed planning for the same requirement is refused. Every paid role shares task/Team admission and accounting. Cost limits prevent runaway work but do not replace adequate tools, dependencies or task scope.

Native harness context and cache reads can still be billed. Bash is an editing/testing tool, not a way to eliminate model tokens. See [the execution/accounting contract](docs/v2-implementation.md).

## Acceptance boundary

Local automated tests exercise the state machine, fresh PostgreSQL schema, budgets, native protocol, ingestion, publication/merge mocks, controls and browser behavior. Real SDK sessions, deployment container isolation, dependency images, backup/restore and a representative paid-task benchmark require the actual deployment host.

No paid task completion, automatic cost reduction percentage, provider invoice reconciliation or universal repository support is asserted by passing local tests.
