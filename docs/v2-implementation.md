# V2 implementation and operations

The [V2 architecture specification](../autonomous_engineering_worker_v2_technical_architecture.md)
takes precedence over legacy workflow documentation.

## Current status

The main fixed workflow is implemented:

1. A scoped, deduplicated import explicitly enrolls an eligible task.
2. A Git-only container prepares the current repository base branch.
3. The Developer uses its native Codex or Claude session to inspect, edit, and test.
4. A separate credential-free, network-disabled container validates and commits.
5. A Git-only container pushes the validated commit; the controller creates or reuses its PR.
6. Authorized review feedback resumes the same native Developer session with a new delta.
7. Current-SHA validation, CI, approval, repository policy, and mergeability are rechecked.
8. A conditional GitHub merge uses that exact SHA, then records completion.
9. A durable tracker-status outbox updates the source ticket's explicitly configured Done destination.

`PUBLISH_PR` and `MERGE_PR` are connected; they no longer deliberately block
as unfinished phases. The default controller lane does not invoke a mandatory
Deliverer → Thinker → Executor → Tester model chain.

**This is not yet a production-accepted V2 installation.** Docker was stopped during
verification. Real container/SDK runs and the authorized 10–20-ticket benchmark
have not been performed. The capabilities endpoint reports
`rollout: operator-gated-validation` and `execution_ready: false` to make that
distinction explicit. Nothing in this change resets historical usage or starts workers.

## Implementation checklist

- [x] Fixed lifecycle, independent status/stage/wait reason, optimistic versions and audit.
- [x] Native Codex/Claude adapters with persisted session IDs and bounded feedback deltas.
- [x] Explicit Team/repository enrollment; existing tickets are never silently converted.
- [x] Signed GitHub, Linear, Trello and Slack ingestion with durable delivery deduplication.
- [x] Linear V2 polling independent of legacy workflow nodes.
- [x] Linear structured webhook assignment/state eligibility; durable Trello/Linear semantic status sync.
- [x] Isolated checkout, deterministic validation/commit, branch push and idempotent PR lookup.
- [x] Authorized, deduplicated review/fix loop; current-SHA conditional merge.
- [x] Missed review/CI webhook rechecks without AI calls.
- [x] Task/Team cost reservations shared by development and cloud interpretation.
- [x] Streaming Codex budget interruption; Claude SDK query budget; incomplete usage preserved.
- [x] Separately metered native compaction; native automatic compaction remains available.
- [x] Local interpreter accounting separate from paid tokens; bounded DeepSeek/OpenAI fallbacks.
- [x] Team/global native cost, time, phase and compaction statistics; legacy dashboard aggregation retained.
- [x] Free UI notes/status and explicit execution commands without a legacy AI responder.
- [x] Orphan inspection/stop for provably owned expired runners, retaining stopped-container evidence.
- [x] Production V2 overlay, same-path binds, private Ollama and destination-restricted provider gateway.
- [x] PostgreSQL tests of new migrations, reservations, lifecycle, feedback dedup and merge orchestration.
- [ ] Real Docker isolation, dependency-image, cancellation and SDK/session/compaction smoke tests.
- [ ] Production-shaped database upgrade/backup/restore test including the legacy pgvector schema.
- [ ] Representative authorized 10–20-ticket functional, cost and recovery benchmark.
- [ ] Optional paid Thinker/Reviewer dispatch and explicit cross-model/cross-harness session migration.
- [ ] Legacy agent-configuration conversion with a reviewed ambiguity report.
- [ ] Legacy runtime/table removal only after benchmark and retention approval.

The last two feature/migration items are not secretly implemented by the fixed profile
editor. Those profiles can be configured, but the default executable lane is the native
Developer plus interpretation and deterministic validation/delivery. A model/profile
mismatch for an existing native session blocks instead of silently replacing the session.

## Boundaries and ownership

| Package | Responsibility |
| --- | --- |
| `engineering/domain` | Fixed transitions and suspension semantics; no framework/provider imports |
| `engineering/application` | Leased phase execution and the native-session development use case |
| `engineering/infrastructure` | Enrollment, durable jobs, lifecycle records, validation and phase controller |
| `agent_runtime/application` | Provider-neutral harness settings and usage receipts |
| `agent_runtime/infrastructure` | SDK adapters, Docker protocol, task lock, reservations, accounting, orphan stop |
| `intake` | Deterministic classification, source authorization, bounded interpretation and event dedup |
| `delivery` | Git-only transfer, authoritative GitHub evidence, conditional merge and periodic rechecks |
| `teams` | Fixed profiles, explicit automation policy, pricing administration and statistics |

Application/domain code does not import SDKs or database models. Bootstrap composes
adapters. The API and controller do not execute repository code or instantiate a native
coding SDK. The developer image contains the optional, pinned harness dependencies.

## Enrollment and current source

An enabled Team policy lists explicit repository UUIDs. Eligible imports can enroll
automatically; existing tickets use the explicit enrollment endpoint/button.
The same policy checks apply to both. Enrollment refuses active legacy execution,
existing workspaces/PRs, manual takeover, archived resources and ambiguous scope.

A new task gets its own standalone repository, controller directory and persistent
native-state directory. Initial checkout fetches the configured base branch at execution
time, not an old RAG index. Its base SHA is persisted. Later feedback keeps the task's
branch/session; it does not silently replace the branch with a newer main/master checkout.
Future tasks fetch the newer branch. Repository RAG is disabled by default and never
required by this V2 path.

Existing tasks with work or a PR need a reviewed migration/recovery decision.
Do not flip `execution_version` in SQL, delete workspaces, or reset usage to bypass checks.

## Native editing, feedback and compaction

Codex and Claude use their own native tools, including terminal/Bash operations,
inside the task container. There is no platform-written patch-generation retry loop
and no web terminal required for coding. Failed edits/tests can be corrected in that
same native turn.

The runner first emits its native session ID. The controller persists it and writes a
fresh acknowledgement into a read-only controller mount before paid work begins.
The next turn explicitly resumes that ID. Only the new feedback is supplied by the
controller, not another accumulated plan/transcript/source bundle.

This does **not** mean every provider request bills only the new delta. The native
harness still manages model context and caching. Cache reads remain billable according
to provider pricing. No measured percentage or dollar saving is claimed without a
real benchmark.

Native automatic compaction is accounted in its turn usage. Optional
`DEVELOPER_COMPACT_BEFORE_FEEDBACK_TOKENS` triggers a separate Codex compaction run
before a long-session continuation; zero disables platform-triggered compaction.
The SDK compaction turn has its own reservation, receipt, duration and
`v2.compaction.1` run record. It preserves pending feedback and the existing session.
Claude's explicit compaction adapter dispatches its native `/compact` command.
Codex's pinned high-level compact API returns a start acknowledgement, so the adapter
uses the pinned notification interface to collect the actual metered turn.

Concurrent requirement updates cannot be erased by a late old-turn receipt.
Unknown native state/usage never starts a replacement session automatically.

## Validation and GitHub delivery

Validation commands are administrator-configured argv arrays keyed by repository
UUID. The validator has no model/GitHub/database credentials and no network. It
captures a bounded output tail, kills timed-out process groups, and detects source
changes made by tests. Passing checks create a local commit; tests that modify source
cannot silently publish an unvalidated change.

**Dependency preparation is an operator prerequisite:** the runner image must already
contain the selected repository's supported tools and dependency caches/environment.
The stock controller image cannot supply every project's Python/Node dependencies.
Build a repository-specific image and use that image for both Developer and validation.
Do not grant validation internet or production secrets to make a dependency error pass.

The credentialed publisher executes fixed Git commands, not project hooks/config.
It exports only validated Git objects into a fresh bare repository, rejects symlinks,
does not import alternates, and pushes only the task branch without force.
The Developer never receives GitHub push credentials. No persistent/global Git identity
or credentials are written by this transfer path.

PR creation first looks up the exact head/base pair. Ambiguous results or mismatched
head SHA stop. Lost responses are reconciled by subsequent lookup, not blind write retries.

GitHub webhooks trigger fresh authoritative reads. Merge requires:

- Team auto-merge enabled and repository explicitly allowed.
- Current head exactly matching the task revision and local validation requirement version.
- Every configured CI check present and successful; missing/ambiguous evidence fails closed.
- An authorized immutable numeric human reviewer ID, excluding the PR author.
- Current-SHA formal approval, no blocking change request, and confirmed mergeability.
- An unsuspended task, available Team, and valid execution lease.

If formal approval is explicitly disabled in policy, an authorized issue comment containing
exactly `/lgtm <current-sha>` is also accepted. Plain “lgtm”, model output, bot identities
and old-SHA comments are not approval. Dismissed/change-requested reviews invalidate the
nonformal fallback for that actor. The final merge request includes the expected SHA.

If evidence changes between review and merge, the task returns to external review wait,
not a paid planning loop. Missed webhooks are rechecked at most once per five minutes
per waiting task. Paused tasks are not resumed by polling.

## Sources and the small interpreter

Signatures are verified over the original bounded body (maximum 1 MB). Delivery IDs and
source/review fingerprints suppress redelivery. A valid provider signature is not
sufficient actor authority.

- GitHub: review/CI/PR webhooks; formal reviews are deterministic. Configured reviewer IDs
  govern actionable comments.
- Trello: signed events wake the authoritative card poller. Authorized comment actors
  come from integration configuration `v2_actor_ids`.
- Linear: signed issue/comment events plus fixed-source polling. V2 polling reads
  `v2_assignee_id` and `v2_source_state_ids` from integration configuration, once per minute.
  Comment actors require `v2_actor_ids`.
- Slack: signed Events API callbacks, configured workspace/channel/actor routing.
  Send `task <description>` or `@app task <description>` in the configured channel.
  Thread replies attach to the existing task. This is not a Slack interactive
  slash-command endpoint.

`SLACK_TEAM_ROUTES` is a JSON object keyed by `workspace-id:channel-id`; each route
contains `team_id`, `repository_id` and comma-separated `actor_ids`.

Structured events and explicit commands do not need a model. Free text is claimed
separately from webhook transactions. Deferred comments do not interrupt a developing
task just to classify it. Authorization and task/SHA relevance are rechecked before action.

When enabled, local Qwen/Ollama is attempted first. Optional
`INTERPRETER_CLOUD_MODELS` contains at most two explicit entries such as
`deepseek/<configured-model>` and `openai/<configured-model>`.
No model name or price is guessed. An explicitly budgeted Team Interpreter cloud profile
can select the first fallback. A configured Ollama profile supplies the local model.

The interpreter gets only bounded event text/reference, no repository, RAG, transcript,
tools or merge authority. Each cloud attempt has a 512-output-token ceiling, a short
timeout, and an admitted cost reservation. There is no repair loop for malformed JSON.
Low-confidence/unavailable interpretation requests explicit human classification.
Local model time/tokens live in `local_model_runs`, not paid API totals.

An in-flight classification does not hold up unrelated queued comments. A classification
claim lost for 15 minutes is marked for human review, not replayed. Expired cloud runs
retain unknown billing until reconciled. A configured Interpreter hard budget is cumulative
per task across cloud fallbacks, in addition to request/task/Team admission limits.

### Source-ticket completion

Each lifecycle change updates a durable `external_status_syncs` outbox in the same
transaction. The controller separately writes only configured semantic destinations:
`todo`, `in_progress`, `in_review`, `blocked`, `paused`, `cancelled`, and `done`.
Trello integration keys end in `_list_id`; Linear keys end in `_state_id`.
For example, set `done_list_id` or `done_state_id` to the exact completed destination.
Paused/cancelled tasks are never silently reported as Done.

Missing configuration is recorded for operator attention. Provider errors back off and
stop after five attempts; they do not trigger an AI run or undo a confirmed merge.
After correcting configuration, `POST /v2/tasks/{id}/retry-status-sync` queues a free
deterministic retry. Repeating an absolute tracker-state update is idempotent.

## Costs and recovery

`ai_runs` keeps normalized input/output/cache/reasoning counters, provider-reported and
catalog-calculated cost, pricing provenance, reserved cost and timing separately.
Missing values remain null. Input includes cache reads/writes; reasoning is a subset
of output, not an extra token category to add again.

A Team lock serializes spending admission. Running reservations count toward task/Team
limits. Suspended tasks/Teams cannot admit new spending. Unknown stopped-run costs block
further Team spending until explicitly reconciled. Reservations are not retrospectively
reported as actual consumption.

Codex streams usage and requests interruption at its configured ceiling; Claude gets
the SDK query budget. **These are interruption/admission controls, not an exact invoice
cap:** an already in-flight provider request can finish or overshoot before interruption.
Use provider-side organization/project limits as an additional financial control.
Long-context/service-tier billing must be represented conservatively in the configured
pricing; this version only selects the catalog's explicit standard-tier entries.

On lost controller leases, owned runners are stopped; workspaces/native state and
stopped-container evidence are retained. There is no automatic paid replay.
A genuine late billing receipt can reconcile an orphan-stopped run without resuming
the task or consuming newer feedback.
An operator can reconcile an unknown stopped run through
`POST /v2/runs/{id}/reconcile-cost`, supplying the actual USD amount and receipt/reference.
This records an audit trail, does not invent token counters, and cannot overwrite a
known cost. Never enter zero simply to unlock a task.

## API and UI

Under `/api/v1`:

- `GET /v2/capabilities`
- `GET /v2/teams/{id}/profiles`
- `POST /v2/teams/{id}/profiles/initialize`
- `PUT /v2/teams/{id}/profiles/{role}` with optimistic version
- `GET /v2/teams/{id}/activity`
- `GET/PUT /v2/teams/{id}/automation`
- `POST /v2/tasks/{id}/enroll`
- `POST /v2/tasks/{id}/retry-status-sync`
- `GET /v2/statistics?team_id=<optional-id>&days=30`
- `GET/POST /v2/pricing` (new immutable version, exact prices, effective date and source URL)
- `POST /v2/runs/{id}/reconcile-cost`

Teams → Open team lifecycle shows fixed profiles, enrollment/policy, queue, task
details, fullscreen canvas and phase milestones. Escape exits native fullscreen.
Team and global statistics separate native/cloud/local measurements and show missing
costs as unavailable. The existing main dashboard and ticket CSV retain historical usage.

Ordinary V2 task-conversation notes make no AI call. Explicit local commands:

- `/status <task-uuid>`: deterministic status response.
- `/pause <task-uuid>`, `/resume <task-uuid>`, `/cancel <task-uuid>`: audited controls.
- `/feedback <task-uuid> <new instructions>`: saves a bounded delta and pauses work;
  inspect interrupted usage, then use Resume. It does not recreate a plan.

The installation retains its existing local-operator access model. Put the API behind
trusted authentication/access controls; this work does not introduce public multi-tenant
authorization. Never expose the Docker socket, private Ollama, or native state publicly.

## Deployment

Use the explicit overlay:

```sh
docker compose -f deploy/compose.production.yaml -f deploy/compose.v2.yaml config --quiet
docker compose -f deploy/compose.production.yaml -f deploy/compose.v2.yaml --profile images build
```

Configure required production secrets privately. Set an absolute `V2_DATA_ROOT`
whose path is identical on the Docker host and inside the controller. This is essential
because the controller asks the Docker daemon to bind those paths. Back up old database,
workspaces and state before applying migrations `0058` and `0059`.

The overlay disables legacy execution and keeps `V2_SCHEDULER_ENABLED=false` by default.
It does not delete legacy data. Start API/frontend without paid workers first; initialize
profiles, publish verified prices, configure repository-specific validation commands,
then set Team/repository/actor policies and the approved USD limit.

The provider gateway exposes only exact TLS CONNECT destinations
`api.openai.com`, `api.anthropic.com`, and `github.com` to private task runners.
It has no keys, database or Docker socket. TLS is not intercepted; it restricts destinations,
not the semantics of an allowed provider request. Actual egress/isolation must still be
tested on the deployment host.

Ollama runs on a private network with no published port, bounded resources and a persistent
model volume. Supply a verified `OLLAMA_IMAGE` tag/digest and prepopulate the chosen model
volume through a separately approved provisioning step; the private service cannot
download arbitrary models from the internet. Do not silently download multi-GB models.

The worker alone needs the Docker socket. Treat it as highly privileged. Runner
UID/GID is 10001, with a read-only rootfs, dropped capabilities, bounded CPU/RAM/PIDs,
fresh read-only authorization mount and shared task file lock. This configuration
requires real host testing; it is not a security certification.
Validation has no native-state bind: it receives an empty, temporary home directory,
so repository tests cannot read persisted SDK state. Git plumbing uses bounded output
capture and process-group cancellation, including transport helpers.

## Verification and acceptance

Verified in this checkout without paid AI calls:

- Backend: 584 unit/application/domain/infrastructure/architecture tests passed;
  Ruff check/format and mypy (381 source files) passed.
- PostgreSQL: 32 integration tests passed, including new migration DDL, atomic
  reservations, stale-worker pause protection, orphan/late-receipt accounting,
  tracker status delivery and the mocked-provider PR/review/merge lifecycle.
- Frontend: lint, formatting, type-check (zero errors/warnings), 35 unit tests and
  production build passed.
- Production Compose overlay validation and `git diff --check` passed.
- Real local Git object-copy/fsck tests passed; the remote push was mocked.

One legacy repository-resource integration test was excluded from the available
PostgreSQL run because the disposable non-vector schema has no `knowledge_chunks`
table. A production-shaped pgvector upgrade remains required; this exclusion is
not a claim that the complete production database suite passed.

Backend unit command: `cd backend && .venv/bin/pytest -q --ignore=tests/integration`.
Database command, **only against a disposable test database**:
`TEST_DATABASE_URL=<test-url> .venv/bin/pytest -q tests/integration --ignore=tests/integration/test_repository_resources.py`.
Frontend command: `cd frontend && npm run check`.

The PostgreSQL migration test executes the
actual new revision functions in a rolled-back unique schema with minimal legacy
prerequisites. It is not a full upgrade of a production-shaped pgvector database.

The lifecycle integration test uses real PostgreSQL records and mocked GitHub responses.
It checks enrollment, phase sequencing, deduplication, same-session feedback, current-SHA
merge admission and one merge write. It does not claim a real SDK edited a real repository.

Before deleting remaining legacy runtime, benchmark 10–20 explicitly selected tickets.
Record ticket complexity, provider/model/harness version, completion, input/output/cache
tokens, actual cost, provider/wall/phase time, repairs, compactions, review cycles, and
recovery outcome. Include small docs/UI work, backend changes, tests that fail initially,
a review fix, paused work, provider failure, stale approval and a merge conflict.

Do not infer savings from old usage deletion or compare unlike task scopes. Include
failed attempts and unknown costs; reconcile those before accepting a benchmark.

Required operator inputs remain: Docker available without waking old paid workers;
a disposable GitHub repository and selected Trello/Linear task; approved provider and
total USD spend; permission for branch/PR writes and any approved merge; verified prices,
validation image/commands, and reviewer/check policy. No production writes or paid
benchmark runs were performed during this implementation.

## Verified interfaces

The OpenAI Docs skill guided native SDK/session/compaction integration; the installed
pinned SDK is also inspected and contract-tested.

- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Codex app-server](https://learn.chatgpt.com/docs/app-server)
- [Claude SDK commands and compaction](https://code.claude.com/docs/en/agent-sdk/slash-commands)
- [GitHub pull-request merge API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request)
- [GitHub review API](https://docs.github.com/en/rest/pulls/reviews#list-reviews-for-a-pull-request)
- [Trello webhook verification](https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/)
- [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/)
- [Ollama chat API](https://docs.ollama.com/api/chat)
- [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/)
