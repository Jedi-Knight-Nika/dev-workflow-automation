# Task execution, token accounting and recovery

## Normal path

A ticket is created without inference. Eligible ingestion or an explicit Start work action checks Team/repository scope, enrollment policy and Developer configuration. Missing configuration creates a visible wait instead of starting a planning retry loop.

Enrollment creates one DeveloperSession record and deterministic phase job. Intake checks scope and prepares current source. The Developer runs inside a separate Docker container using the pinned Codex or Claude SDK. Its own tools inspect, edit and test the checkout.

The native ID is persisted before the controller acknowledges permission to execute. On continuation the controller resumes that ID and supplies only new feedback. The native harness retains its history; the application does not reconstruct and resend a complete transcript.

## Optional planning and review

Developer output can request NEEDS_PLAN. An enabled Thinker runs read-only with its own native home and receipt, returns PLAN_READY plus a bounded artifact, and the Developer continues with that artifact. A completed plan for the same requirement is not repeatedly purchased.

After deterministic validation, an enabled Reviewer reads source in a separate read-only native session. REVIEW_CHANGES returns bounded feedback to the existing Developer session. REVIEW_OK permits publication, not merge authorization. These roles need their own explicit profile limits and count against the same task/Team allowance. They are off by default.

No application-side JSON file-generation/patch-repair loop exists. Native tool failures can be corrected within the ongoing coding turn.

## Validation and publication

Validation runs administrator-configured argv commands in a separate no-network, credential-free container. Its image must already contain required languages, packages and caches. A timeout kills its process group; output is bounded. Tests that modify source invalidate the checked result.

Passing checks create a commit. A Git-only transfer container exports the validated objects and pushes only the task branch. The controller creates or reconciles the matching PR. GitHub credentials are not provided to the Developer or validator.

Provider approval and CI are not inferred from local test success. Remote evidence is fetched again and tied to the exact head SHA and requirement version.

## Review and merge

Signed events are durably deduplicated. Structured reviews/checks and exact commands are handled deterministically. Relevant authorized free-text feedback may use the local interpreter and explicitly configured cloud fallback.

Feedback received during an active phase is deferred; paused tasks stay paused. Actionable feedback resumes the same Developer with a delta. Requirement changes increment version, record actor/history and invalidate prior evidence.

Merge requires all configured gates: enabled Team, runnable task/lease, allowed repository, auto-merge policy, exact current SHA, current local validation, required successful CI checks, authorized human review and mergeability. Formal approval is the default. Teams can explicitly allow any human GitHub reviewer, including the PR author, instead of an ID allowlist. When nonformal approval is enabled, common exact approval phrases are classified without inference; other wording uses the bounded Interpreter and requires at least 0.95 confidence for approval. The exact current-SHA `/lgtm` command remains supported.

The controller fetches human comment/review snapshots directly from GitHub, binds them to the validated commit and stores their body digest, author and update time. Unclassified messages block merge. The final merge job fetches the evidence again, so edited/deleted comments and changed revisions cannot reuse an old interpretation. Human comments must follow validation; bots never supply approval. GitHub pause/resume/cancel commands still require explicit actor IDs even under any-human reviewer scope.

The final GitHub merge request includes the expected SHA. If evidence changes, the task returns to review wait. Waiting/polling does not create paid planning runs.

## Cost contract

AIRun records role, provider, model, native IDs, requirement version, timestamps, reservation, usage completeness, token categories, provider/calculated cost, failure and bounded artifact. Local Ollama runs are separate and not counted as paid API tokens.

Before paid inference, the controller reserves against current role, task and Team cumulative allowances. A running or unreconciled unknown-cost run prevents an unsafe second admission. Known pre-inference failures can be zero; lost receipts remain unknown until explicitly reconciled with evidence.

Codex streaming usage is watched against configured pricing and the turn allowance. Claude uses the SDK budget plus normalized receipts. An in-flight provider request can overshoot the requested limit before interruption/receipt arrives; this is not a guarantee of an exact provider invoice cap.

Native compaction usage is metered. Optional platform-triggered compaction has its own reservation and receipt and preserves pending feedback. The default threshold is zero, leaving native automatic context management in place.

A pause, resume, Team wake or model change never resets historical usage. Changing a model/harness requires a suspended task, version checks and explicit operator reason. A compatible same-harness model change can retain its native ID; a cross-harness change creates a generation with a bounded handoff, not an imported transcript.

## Why this uses fewer avoidable tokens

- No mandatory multi-role model chain for routine work.
- No repository index/embedding dependency or whole-source prompt injection.
- Current files are read only when native tools need them.
- Native edit/test correction happens in the same coding session.
- Feedback is a bounded delta, not repeated plans and memory.
- Deterministic routing, polling and UI notes are free.
- Optional consultations are bounded and separately metered.
- Missing tools/configuration and unknown spending stop with evidence instead of blind retry.

These remove identifiable overhead, but do not promise a measured saving. Native context, tools, cache reads and compaction still cost tokens. Compare completed task cost and success rate, not just whether a budget stopped a run.

## Stopping and resuming

Ticket pause revokes current leases and preserves phase/source/session. Cancellation is terminal; archive hides terminal tickets without erasing evidence. Manual takeover stops automation until explicitly released.

Team Stop work sets execution_paused, revokes leases and pauses tickets while keeping the Team enabled. Workers observe lease loss and stop owned runners. Enable execution clears admission pause but does not automatically resume suspended tasks.

No control can instantly undo an external request already accepted by a provider. Cancellation is coordinated through leases, heartbeat interruption and owned-container cleanup; current-SHA checks prevent a late stale result from advancing the task.

## Diagnostics

Use the ticket's status history, latest job failure, validation output and AI run artifact. Job SUCCEEDED means its execution unit completed; MERGED is the delivery outcome.

Read-only monitoring:

```sh
python scripts/validate_real_workflow.py TRELLO-example --poll-seconds 15
```

The observer performs GET requests only. It never starts, resumes, retries, resets budgets or merges. It prints task state and metering/evidence when work finishes or suspends.

## Verification and remaining deployment acceptance

Local verification covers backend architecture/types/lint, unit and PostgreSQL integration tests, frontend checks/build, and mocked-API browser flows including fullscreen and receipts.

Docker acceptance now covers isolated validation, cancellation, Caddy and backup/restore.
One paid Codex documentation task resumed its native session, passed offline checks, and
opened a PR for approximately $0.091. See [the verification record](refactor-verification.md)
for exact evidence, fixes and caveats. Real reviewer/CI-authorized merge, other configured
harnesses, compaction and the 10–20-task benchmark still need deployment acceptance.
Record completion rate, cost per completed task, context/cache/compaction usage, latency
and failure categories; do not extrapolate savings from this single small task.

Model discovery for the optional DeepSeek interpreter uses its [documented GET /models endpoint](https://api-docs.deepseek.com/api/list-models/). Provider model availability/prices must be verified by the operator; no static discovery list or price is guessed.
