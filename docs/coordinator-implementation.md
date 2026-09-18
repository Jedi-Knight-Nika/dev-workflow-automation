# Coordinator implementation and rollout

The modular monolith now has an independent, event-driven Coordinator. The bounded engineering engine, validator and merge policy remain authoritative for code delivery.

## Runtime

Verified provider deliveries already enter `webhook_deliveries`. Task-bound comments then enter `coordinator_events` after routing and actor checks. Dashboard messages use the same inbox. A short debounce coalesces events; PostgreSQL task locks serialize claims across controller replicas. The model runs outside database transactions. Decision and effect workers run independently, so an in-flight model request does not stall queued delivery. Decisions and their context are durable in `coordinator_runs`; a separate executor checks authority and current revisions before applying a single semantic action. `coordinator_actions` also acts as the reply outbox.

The model can read task details, discussion, PR state, reviews, inline review feedback and current CI checks. It can reply, publish a summary note, ask a question, request implementation/repair or validation of a completed Developer candidate, pause/cancel work, request configured GitHub reviewers, or request synchronization of the authoritative lifecycle status. Summary notes never overwrite the source requirement. Status intents reuse the existing durable status outbox and configured tracker state IDs. It cannot supply destination IDs, execute arbitrary APIs, change budgets, or authorize a merge. The normal context contains the original requirement, current state, recent messages, check results and a small checkpoint. Oversized situations stop visibly rather than dropping the original requirement.

Shadow mode records proposals alongside the existing behavior. Active mode owns the selected conversational flow, so the old prose classifier does not also apply that event. Explicit task controls and deterministic approval/merge processing remain in their existing paths. Engineering start/completion, validation, publication, merge, cancellation and blocking events can wake the Coordinator to report results. Reconciled GitHub PR/CI evidence enters the same inbox. Formal requested changes enter coordination when GitHub coordination is active; approval and merge authority remain deterministic.

Human questions create a version-bound `HumanRequest` and release engineering jobs. Dashboard answers and authorized replies in the same task conversation wake coordination; a work decision revises the requirement and queues the existing engine. The Dashboard and Team pages show working, queued, human-waiting, external-waiting and backlog lanes, priorities, slot usage and spending. A separate Recently completed lane shows the latest 20 merged tasks from the past seven days, scoped to the selected Team and independent of open-queue pagination. The task page shows the question, conversation, decisions and failed effects. Queue results are bounded and paginated.

## Enable

Use the existing execution deployment overlay and `scripts/start-local.sh` procedure. The worker requires `SCHEDULER_ENABLED=true`; a dashboard-only launch does not execute jobs. Migration `0008_coordinator` is additive and is applied by normal startup migration handling. No live deployment is performed by these code changes.

Start with these settings, after configuring the provider credential, verified model price, Team enrollment/repositories, Developer profile and validation commands:

```dotenv
COORDINATOR_MODE=shadow
COORDINATOR_PROVIDERS=["dashboard","trello"]
COORDINATOR_PROVIDER=openai
COORDINATOR_MODEL=gpt-5.6-luna
COORDINATOR_REQUEST_LIMIT_USD=0.05
COORDINATOR_DEBOUNCE_SECONDS=3
GLOBAL_DEVELOPER_SLOTS=2
VALIDATION_SLOTS=2
SCHEDULER_MAX_CONCURRENT_JOBS=6
```

Shadow mode purchases model inference but sends no provider replies and changes no task state. Switch `COORDINATOR_MODE=active` to apply decisions for the listed providers. Add `linear`, `github` or `slack` to that list when their routing/actor policy is configured. `off` prevents new Coordinator purchases and effects. A zero-event idle worker makes no model calls. Environment changes require restarting both API and worker so their routing modes agree.

Trello/Linear conversational actors must be in integration `configuration.actor_ids`; GitHub uses the existing immutable reviewer IDs/policy. Verify the Trello or Linear connection to record the integration identity used to distinguish its own message echoes. Configuration updates merge fields, preserving routing and actor settings that forms do not edit. Linear intake now exposes its actual assignee/source-state requirements. Trello polling honors the configured interval.

Slack credentials are available on Integrations and are verified with `auth.test`. Configure `SLACK_SIGNING_SECRET` and `SLACK_TEAM_ROUTES` on the server. Existing `/task ...` message/app-mention intake binds the Slack thread to a task. Replies stay in that thread. Grant `chat:write`; thread reads also require the token type and conversation history scopes appropriate to the conversation. A successful credential check does not prove access to every thread. Read failures are returned to the Coordinator as unavailable evidence. See [Slack auth.test](https://docs.slack.dev/reference/methods/auth.test/), [thread replies](https://docs.slack.dev/reference/methods/conversations.replies/) and [message posting](https://docs.slack.dev/reference/methods/chat.postMessage/).

## Spending and scheduling

All Coordinator inference uses `ai_runs`, existing verified pricing and Team/task admission. An optional `ACCOUNT_MONTHLY_BUDGET_USD` adds an account-wide UTC-month ceiling. Team policy exposes a monthly hard ceiling and a daily soft allowance. Existing cumulative Team/task and per-generation limits still apply. Running reservations count before purchases, including unsettled work from an earlier month. Unknown cost stays unknown and blocks further admission until reconciled. The daily allowance is visible guidance, not an automatic budget increase.

The global admission lock covers only a short claim transaction. Within a priority bucket, the least recently served eligible Team receives the next slot; oldest work within that Team wins. Existing numeric priorities retain their lower-number-first convention. Validation has its own global capacity. Local controller concurrency must leave room for validation/publication alongside paid jobs. Integration reconciliation runs independently from job dispatch.

Native progress snapshots include PRODUCTIVE / MARGINAL / STALLED / REGRESSING classifications. Bounded multi-patch work now uses this evidence to control actual repair spending: one initial repair is available; further repairs require a strict reduction in failing deterministic checks. Repeated unresolved checks or new failing checks stop the work unit. Each unit has a four-attempt ceiling, and every call still passes the existing shared 16-call, input-token and USD admission checks. A productive repair can request medium effort within the Developer profile and Team ceilings. A stalled unit may request one fresh read-only investigation and replan of the remaining work. Completed contracts and edits are retained; the six-unit and 16-call allowances are not reset. Regression, uncertain usage, unavailable tools, or invalid file authority stop execution. Repair packets narrow prior work to completed contracts and the latest failure while preserving the complete requirement. Set `adaptive_replans=0` to disable this transition. No model/provider change or budget increase is implicit. Routine FAST_PATCH retains its initial patch plus one repair; the native tool-loop governor retains its existing policies.

## Explicit model routing

The Team token policy editor has optional planning, investigation and repair model overrides. Each route records provider, exact model ID, allowed adaptive modes, default/max effort and experimental status. Routes use the Developer's provider and require verified catalog prices before the turn is admitted. DeepSeek additionally requires explicit experimental opt-in. FAST_PATCH keeps the selected Developer model.

Each request uses its selected price for admission under the same generation reservation. Every request records its model, price ID and usage. The controller persists admitted price IDs before inference and recomputes settlement from those catalog entries, verifying that per-request token counts equal the aggregate receipt. Mixed-model runs retain individual identities and are labeled `multiple-models` at the aggregate level. Unknown or inconsistent billing stops delivery and keeps spending reserved. Routing cannot expand provider credentials or raise Team/profile effort limits.

## Experiments

Canonical handoffs use a versioned `AgentEnvelope`, including task/revision/SHA and structured payload. The controller consumes Coordinator guidance, binds the full work request to the runner manifest, and requires a typed result tied to the same task, requirement, input SHA and receipt ID. The manifest transports the requirement once. Native SDK prose is normalized at the runner boundary; delivery decisions consume the typed outcome. Invalid artifacts fail the turn while valid usage is retained for billing. Full validation remains mandatory. Lossless JSON_VERBOSE, JSON_COMPACT, DSL_V1 and COMPRESSED_V1 codecs are available for evaluation; experimental codecs do not replace the production JSON contract by default. COMPRESSED_V1 uses a bounded dictionary for repeated structural keys, with explicit escaping and rejection of duplicate decoded keys. Human prose, source and exact errors round-trip unchanged; fewer bytes are not claimed to mean fewer model tokens.

Run the free codec check from `backend`:

```sh
.venv/bin/python -m evaluations.benchmark_coordinator --output /tmp/coordinator-codecs.jsonl
```

The six synthetic cases cover scope feedback, a status question, clarification, waiting CI, attempted authority injection and a missing product decision. They are regression fixtures, not historical production replay evidence. Output distinguishes UTF-8 bytes from actual provider tokens; offline output deliberately leaves token/semantic/patch metrics unknown.

A live experiment requires `--live --max-cost-usd 1 --pricing /path/to/verified-prices.json` and provider keys in its environment. Select models with `--models provider/model ...`. Price entries use the exact model key and `input_per_million`, `output_per_million`, `cached_input_per_million`, `cache_write_per_million`, `source_url`. Supply current verified prices. Every admitted request and receipt is written and flushed before continuing; unknown responses stop the run, and an existing output file cannot be reused accidentally. This standalone evaluation never executes task actions or patches. Actual patch acceptance and repair quality must be measured with the existing engineering evaluation workflow before adopting a new codec/model for coding.

DeepSeek's current [V4.1 Flash release](https://www.deepseek.com/en/news/deepseek-v4-1-flash/) documents `deepseek-flash`. It is labeled experimental when returned by provider model discovery, and can be explicitly selected for Coordinator/interpreter evaluation with verified pricing. There is no silent cross-provider escalation. Developer profiles can now explicitly select DeepSeek with the bounded `patch` harness. Both fast and adaptive paths use the same deterministic source tools, isolation, cost admission and validators as OpenAI. The provider adapter uses DeepSeek JSON mode and locally validates artifacts; incomplete output or unknown usage stops execution. Medium effort maps to DeepSeek low, avoiding an implicit upgrade to high. Rebuild the runner image for the new provider environment/egress contract. No coding default changes or quality superiority are assumed. See the [DeepSeek request contract](https://api-docs.deepseek.com/api/create-chat-completion/).

## Recovery and remaining validation

An interrupted model purchase is not silently repeated. An interrupted/uncertain outbound POST becomes `UNKNOWN`, visible on the task. A single automatic read-only reconciliation checks for a unique recent message from the verified integration identity. The dashboard can queue another “Check delivery” without resending. Missing history, ambiguous matches or unavailable identity leave the effect unknown. GitHub review-request uncertainty requires inspection of review history because a reviewer may already have answered or been removed. Known effect IDs and matching integration-identity echoes suppress repeat wakeups; providers without a reliable idempotent send cannot promise exactly-once network delivery. No automatic resend occurs after uncertainty. Inspect the remote conversation and usage before explicitly requesting another action. An authenticated webhook confirmation wins over a later network timeout. Delivery verification cannot make an uncertain purchase repeat.

Automated coverage exercises real PostgreSQL migration/reflection, dedupe/coalescing, shadow behavior, clarification and resume, current-revision rejection, no retry after unknown delivery, multi-controller global capacity/fairness, periodic reservations, provider destination contracts and codec round-trips. These checks use mocked model/provider responses. Real provider permission smoke tests and paid model quality comparisons remain rollout validation; no external-service result is inferred from mocks. Docker runtime, backup/restore and authenticated proxy acceptance are tested separately without inference.

Feedback arriving during a paid Developer generation retains a `WAITING_ENGINEER` action. After usage settles, it is applied if its state is still current, or the original event is reconsidered against the newly completed work. This is a progress-triggered decision, not an idle paid retry. Unknown settled usage still requires reconciliation.


## Historical replay and accepted outcomes

Export real recorded situations using a read-only database transaction:

```sh
.venv/bin/python -m evaluations.export_history --output /tmp/coordinator-history.jsonl
```

The exporter uses `DATABASE_URL` (override its environment variable name with `--database-url-env`). It preserves the exact recorded situation and its hash. `recorded_action` is an observation, never ground truth. Review each case, fill `expected_actions` and set `label_source` to `HUMAN` before a live comparison. Supply this file with `benchmark_coordinator --cases /tmp/coordinator-history.jsonl`; offline codec replay works without labels or provider calls. Files may contain task prose and should be kept with the same access controls as task history.

To compare actual coding outcomes, run the same cases through the existing bounded engine using the profiles under evaluation, then export the selected task UUIDs:

```sh
.venv/bin/python -m evaluations.delivery_outcomes --task-ids UUID1 UUID2 --output /tmp/delivery-outcomes.jsonl
```

The read-only report includes actual per-request routed model identities, first full-validation batch outcomes where recorded, requirement fingerprints, current-revision validation, observed merge acceptance, failed validation checks, generations, total workflow tokens/cost, human takeover and time to merge. It does not dispatch coding, count an unfinished task as a failed delivery, infer first-pass acceptance from targeted checks, or treat missing usage as free work. Compare matching case/revision cohorts and keep mixed-model or human-assisted runs separate before drawing conclusions. A merged result is an observed delivery outcome, not proof that every product requirement is correct.

## Operational visibility

Prometheus now exposes retained event/run/action/human-request states, oldest pending event age, events per wake, Coordinator known cost/unknown usage, paid-slot occupancy/capacity, recent queue wait and waiting-Team count. Metrics reuse the existing 15-second cached scrape projection and contain no task IDs or message bodies in labels. Unknown costs remain separately visible instead of becoming zero-cost successes. Operator action assessments in the task activity drawer record the latest CORRECT/INCORRECT label per action; incorrect-action rate uses only labeled actions. Additional metrics cover clarification, explicit operator overrides, accepted terminal tasks, first full-validation batch pass rate, repair requests, manual takeover, time to PR/merge, and total terminal-workflow cost/tokens per accepted delivery. Unobserved rates are NaN, not fabricated zeroes; validation coverage is exposed because historical batch outcomes are not inferred from targeted checks.

GitHub review requests are restricted to one to ten configured immutable human reviewer IDs; the current open, non-draft PR head is refreshed before the request. Existing requested reviewers are not requested again. Slack actor permissions are checked against the task's exact workspace/channel route.


## Verification of this implementation

Local verification on 2026-09-14: 754 backend tests passed with real PostgreSQL integration and migration checks. The opt-in Docker suite passed separately: eight runtime/isolation tests and two deployment tests covering full database/runtime-state backup restoration and the authenticated reverse proxy. Backend lint, formatting and strict type checks include the evaluation scripts. Frontend lint, formatting, type checking, all 51 unit tests and the production build passed; the existing execution-window ARIA warning remains. The synthetic codec replay round-tripped all 24 case/codec combinations. This is not a paid model quality result.

The repeatable unpaid deployment stack is `deploy/compose.acceptance.yaml`. It has no inference workers or provider keys, uses an ephemeral in-memory PostgreSQL database, and separates the internal API network from the test proxy's ingress network. Build the runtime test image with `docker build --target developer-runner -t engineering-acceptance-developer:local backend`; start the stack with `docker compose -f deploy/compose.acceptance.yaml up -d --build --wait`, then run `RUN_DOCKER_ACCEPTANCE=true .venv/bin/pytest -q tests/docker` from `backend`. Stop only this stack after the checks. Docker's existing persistent storage was full during verification; no unrelated images, volumes or containers were deleted.

## Completion boundary

The remaining implementation gaps are now connected: typed work/result execution, one evidence-based replan, narrower repair context, explicit role model routing with verified settlement, guarded validation intent, all four experimental codecs, completed-task visibility, and operator-labeled quality measurements.

Still requiring real deployment inputs: provider permission/delivery smoke tests in designated conversations; human-labeled historical cases and a funded model comparison; representative coding outcome cohorts; and activation of shadow/active coordination on the intended runtime. Those are rollout and measurement gates, not claims proven by the unpaid tests. No provider messages, paid benchmark purchases or changes to the running production deployment were made by this completion pass. Changes remain in the working tree for review.

## Offline bug review — 2026-09-14

Accepted conversational changes previously lived only in disposable Developer feedback. They now persist as authorized requirement events, separate from tracker-owned title and description. Developer, Coordinator, Supervisor, consultation and rollover contexts read the same complete requirement history. Tracker polling cannot erase accepted additions. Oversized requirements fail before inference without silently truncating scope or blocking later tasks in the Coordinator queue. Delivery comparison fingerprints include those additions.

Developer and consultation admission now account for an in-flight Coordinator reservation without falsely treating it as a second coding turn or unknown charge. Unsettled failed receipts still block further spending, and concurrent coding turns remain excluded. Failed Developer turns retain pending feedback and clear older cached completion. Validation requests check the latest settled receipt and its task/revision/turn binding instead of trusting a stale checkpoint.

Clarification answers are authorized before changing request state. Coalesced follow-ups preserve the original answer, and only events bound to that question can continue its blocked task. Effect admission rechecks every coalesced event's provider authority and GitHub head. Unauthorized messages cannot redirect engineering notifications; engineering read tools use the originating conversation. WAIT produces no outbound message even when the model supplies prose.

The conversation composer preserves text typed during an outstanding send. A successful save followed by a failed refresh reports that the message was saved and does not leave the original text ready for accidental resubmission. Task navigation resets the composer and discards late message pagination from a different task. ESLint excludes generated Playwright artifacts so browser runs cannot race its directory scan.

Verification for this review: **768 backend tests, 51 frontend unit tests and two mocked Chromium regression tests passed**. Backend lint, formatting and strict type checks, frontend lint/format/type checks and the production build passed. Existing warnings remain: Starlette's deprecated AnyIO alias, the execution-window ARIA warning and the frontend bundle-size advisory. Tests used an isolated local PostgreSQL database and mocked providers. No live service calls, paid inference, production deployment or Docker acceptance rerun was performed during this review.

## Recovery and dashboard bug review — 2026-09-15

A repair waiting for a paid Developer turn previously prevented the Coordinator from considering newer messages. New input now wakes that waiting action and supersedes its old decision, allowing a fresh pause or cancel decision without waiting for coding to finish. With no new input, the action remains idle. Existing workspace and billing guards still apply; cancellation does not manufacture a settled usage receipt.

Coordinator evidence now excludes clarification questions and validation records from older requirements or lifecycle/head revisions. Delivery reconciliation has a 45-second total deadline, so a stalled provider read cannot monopolize the effects worker indefinitely. A matching authenticated provider echo can confirm delivery while history reconciliation is in progress. Timeout recovery leaves delivery uncertain and does not resend the message.

Task URL changes immediately clear the old task controls, drafts and coordination mode. Each refresh has a generation, preventing older responses from overwriting a newer task snapshot or a completed command's refresh. Unmounted Coordinator panels cannot change the next task's mode. Message bursts larger than the latest page restart history pagination so skipped messages remain reachable; pagination also ignores superseded cursors and merges duplicate IDs safely.

Verification: **773 backend tests, 51 frontend unit tests and five mocked Chromium regression tests passed**. Backend lint/format/strict type checks and the frontend lint/format/type checks and production build passed. Existing non-failing warnings remain. The isolated test database was stopped afterward. No live provider requests, paid inference or production deployment were used for this review.

## Shared code cleanup — 2026-09-15

Repeated logic now lives with the area that owns it:

- `agent_runtime/infrastructure/cost_queries.py` supplies SQL expressions for settled costs, active reservations and unsettled usage. Spending admission, recovery, session changes, consultation and reporting reuse them. Their existing filters, transaction boundaries, locks and treatment of unknown/zero cost remain intact.
- `coordinator/infrastructure/authority.py` owns provider mode and actor authorization. Ingestion, decision processing and action execution use the same checks. `queries.py` owns the common current-question query and event-batch requeue operation; callers retain responsibility for transactions and locking.
- `interfaces/http/errors.py` translates the identical missing/conflicting service errors used by five endpoints. Their existing 404/409 codes and error details are preserved. Endpoints with different contracts keep their specific handling.
- `frontend/src/lib/live-refresh.ts` provides the shared latest-request guard used by the dashboard and task page. `task-messages.ts` merges task history for both polling and pagination with the existing ordering and duplicate handling.

This is a refactor of existing behavior. It adds no dependencies, schema changes or services. Verification passed unchanged: **773 backend tests, 51 frontend unit tests and five mocked browser regressions**, along with lint, formatting, strict backend/frontend type checks and the production frontend build. Checks were local with mocked provider responses; no deployment or live integration calls were performed.

## Integration and refresh cleanup — 2026-09-15

The twelve Linear/Trello workflow destination fields now reuse `components/integrations/DestinationSelect.svelte`. Provider forms still own their state, labels, available destinations, empty selections and saved configuration. Linear destination labels are computed once per state-list change. Existing member selection, source filters, repository selection and text-field fallbacks are retained.

`services/task-updates.ts` now owns the repeated initial refresh, event/poll subscription and cleanup setup used by the queue, Coordinator panel and task detail page. The existing coalescing delay, polling interval and connection callbacks are retained. The Coordinator panel also shares its local pending/error handling between delivery checks and action assessments.

Integration verification uses one identity/configuration merge for Linear, Trello and Slack. Resource access is still checked first for Linear/Trello; saved credentials and unrelated configuration remain intact. Regression tests check the existing provider-call order and configuration behavior without network access.

Verification: **776 backend tests, 51 frontend unit tests and 11 mocked browser checks passed**. The browser checks include all twelve workflow destination bindings, saving IDs/cleared selections, connection failure recovery and the previous task navigation/conversation regressions. Lint, formatting, type checks and the frontend production build passed. Existing non-failing warnings remain. No dependencies, database schema, live integrations or deployment were changed.

## Dead-code audit — 2026-09-15

Reviewed repository references across backend modules, frontend routes/components, desktop startup, scripts, migrations, dependencies and deployment configuration. Backend modules remain reachable from the HTTP, scheduler, isolated runner, migration registry or operator CLI entry points. Framework registration, serialized enum values, dynamic theme translations, database drivers and the desktop plugin's automatic external-link handling were retained.

Removed the unused generic `Card` component, the standalone debounce helper and its three helper-only tests, unused global styles/animations, eight obsolete GitHub event constants, and the unused Observer usage wrapper and chart/card event hook. The backend Observer HTTP endpoints and existing conversation flows remain intact. Removed 204 unused translation keys from each language; all 439 retained English and Georgian entries were compared with their previous values and are unchanged. The product description now reflects the remaining Observer interface.

Two older browser tests had stale selectors: the automatic-merge switch now uses its visible label, and the lifecycle fullscreen button is scoped to the main content. Their saved-policy, reload and fullscreen/no-write assertions are preserved.

Verification: **776 backend tests and 48 frontend unit tests passed**, along with backend/frontend lint, formatting, type checks and the production frontend build. All **16 mocked browser scenarios passed** across the final suite run (15) and the corrected approval-policy test's focused rerun (1). The unit-test count fell by three because the unused debounce helper and its exclusive tests were removed. Existing non-failing warnings remain. The isolated test database was stopped. No live provider calls or deployment were performed.
