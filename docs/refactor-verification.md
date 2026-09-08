# Refactor verification record

Verified locally on 2026-09-08. This records tested boundaries and one live task,
not a general production-readiness or cost-saving claim.

## Passed

- Backend: 356 passed, 22 skipped inside the API image against isolated PostgreSQL 16;
  host suite: 328 passed, 50 skipped (native SDK contracts included; Docker/database opt-ins skipped).
- Backend Ruff, formatting and strict mypy passed.
- Fresh initial schema/default entities initialized in both the isolated acceptance
  database and the explicitly authorized new application database.
- Frontend ESLint, Prettier, Svelte/TypeScript checks and production build passed
  using the supported Node 22 Docker image.
- Frontend unit tests: 32 passed.
- Chromium browser tests with mocked API: 5 passed, including saving/reloading any-human approval policy.
- API, worker, native Developer and frontend Docker images built and ran.
- Real non-root Docker validation/commit, failure preservation, test-mutation rejection,
  timeout/cancellation cleanup and helper read-only boundaries passed.
- Real Codex app-server login/start/inspect passed with a fake key and no network;
  no credential file was persisted. Claude binary startup passed, not a paid Claude turn.
- Caddy authentication and unsigned-webhook rejection passed in Docker.
- Actual PostgreSQL backup/restore scripts restored database and all three runtime
  directories into an isolated destination; overwrite refusal passed.
- Backup/restore shell syntax checks and git diff whitespace checks: passed.

Browser coverage includes explicit start consent, zero estimates, concurrent worker refresh,
ticket actor/time/receipt visibility, responsive notes and fullscreen queue/milestones.

Backend coverage includes fixed phases, optional planning handoff, helper receipt/session
separation, read-only mounts, Team shutdown without deactivation, idempotent start, fair
claiming, source eligibility/dedup, same-session feedback, reservations and conditional merge.

## Live Codex task

- Ticket: `2bde516e-47b5-4708-aa20-f5d8f4987055`, `V2-LIVE-SMOKE-20260908`.
- Scope: an English first-task smoke-test document and its README link, not a feature benchmark.
- Developer model: `gpt-5.6-terra`, low effort; optional Thinker/Reviewer disabled.
  Cloud interpretation was disabled for development, then configured for the approval continuation below.
- Operator authorized at most $3 additional spend; task/Team admission was configured at $2.
- Native thread `01a08044-09fa-7543-a2fe-bb8709aae623` survived the initial failure and
  resumed with only new feedback, not a new planning chain.
- Successful turn: 102,838 input tokens, 1,889 output tokens, complete normalized receipt.
  Calculated cost: **$0.09083430**, including cache-aware prices. This is not an invoice claim.
- Offline document assertions and whitespace validation passed. The controller committed
  and published revision `5f05919085300041c10f2b50ad720a8153075dd5`.
- [PR #3](https://github.com/Jedi-Knight-Nika/dev-workflow-automation/pull/3) opened successfully.
  GitHub Backend, Frontend and Quality gate checks all succeeded at that revision.
- The initial review wait was resolved after the operator explicitly requested any-human,
  normal-language approval and automatic merge. Final workflow state: `MERGED / COMPLETE / NONE`;
  GitHub independently confirmed PR #3 was merged.

### Any-human approval continuation

- Completed and deployed the Team reviewer-scope setting, human-message interpretation,
  snapshot persistence/deduplication and final GitHub evidence recheck.
- The Default Team now has `reviewer_scope=any_human`, `require_formal_approval=false`,
  auto-merge enabled and required checks `Backend`, `Frontend`, `Quality gate`.
  Repository scope and both $2 task/Team budgets were preserved.
- Configured the existing OpenAI `gpt-5.6-terra` Interpreter with a $0.10 per-task role limit.
  Two live metered classification checks passed: unconditional approval was `APPROVAL`,
  and approval conditional on fixing a failed test was `FEEDBACK`, both at 0.99 confidence.
  These synthetic checks were audited and did not become PR feedback or Developer work.
- Those checks cost $0.00180600; combined recorded task cost is **$0.09264030**.
  The original human `lgtm` comment (`5582809479`) was interpreted without inference.
  The controller rechecked the same validated revision and green CI, then merged it.
  No additional Developer turn or native-session reset occurred.
- Regression coverage includes edited/deleted comments, stale revisions, bot authors,
  allowlist/formal-policy restrictions, failed CI, blocking/dismissed reviews and paused tasks.
  PostgreSQL tests exercise polling → deduplicated interpretation → final merge, including
  comment edits/deletion or CI failure between authorization and execution.

### Failures found by live acceptance

1. Populated JSON Compose settings acquired an extra closing brace from the default syntax.
   Optional JSON values now use blank interpolation plus typed settings defaults; malformed
   nonempty values still fail validation.
2. The native Codex app-server was not logged in merely because `OPENAI_API_KEY` was injected.
   The adapter now explicitly logs in before start/resume, using process-only credential
   storage verified against pinned SDK/CLI 0.147.0. Safe provider failure codes reach receipts.
3. Task checkout Git metadata had incorrect ownership on this Docker Desktop host. The
   operator repaired only that checkout; read-only Git object packs were preserved. No global
   Git configuration or source content was changed. An unpaid workspace preflight now checks
   Git access in the runner before native login/inference.

The first turn failed with HTTP/WebSocket 401 before inference. Native records showed zero
tokens and no token-count event. Its unknown cost was explicitly reconciled to zero with a
task audit event; the proven zero native baseline was restored separately with evidence.
The failed run and its missing usage counters were retained, not deleted or fabricated.

Authentication follows the [official app-server login flow](https://learn.chatgpt.com/docs/app-server).
The selected model's rates were checked against its
[official model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra).

## Reproduce unpaid deployment acceptance

```sh
docker compose --env-file /dev/null -p engineering-acceptance -f deploy/compose.acceptance.yaml build backend worker developer frontend frontend-checks
docker compose --env-file /dev/null -p engineering-acceptance -f deploy/compose.acceptance.yaml up -d --wait postgres backend frontend
docker compose --env-file /dev/null -p engineering-acceptance -f deploy/compose.acceptance.yaml run --rm backend-checks
docker compose --env-file /dev/null -p engineering-acceptance -f deploy/compose.acceptance.yaml run --rm frontend-checks
cd backend
RUN_DOCKER_ACCEPTANCE=true .venv/bin/pytest -q tests/docker
```

The host test environment needs the locked dev dependencies and Docker socket access.
Docker tests use their own fixtures/database/project. They do not inherit application secrets
or start inference. Native SDK unit contracts also require the `harness` extra; the API image
intentionally omits these SDKs and skips those contracts.

## Data and actions

With explicit user permission, a new `engineering_worker_v2` application database was
initialized in the existing PostgreSQL service. Saved GitHub/OpenAI connections and repository
metadata were copied; the previous database was left intact. `.env.native` points to the new
database and `.runtime` stores task checkouts/native state. Both are ignored/protected local
data, not committed configuration. Root `.env` still points to the previous database.

Superseded by the V2.1 consolidation on September 8: the redundant legacy/test
databases were deleted with operator authorization, the native database was renamed
`engineering_worker`, and its runtime and monitoring configuration moved into `.env`.
Plain `docker compose up -d --build` now selects the complete local stack through
`COMPOSE_FILE` and `COMPOSE_PROFILES`; there is no separate preview database.

## Remaining acceptance / caveats

- A real review requiring code changes followed by revalidation and approval remains to be
  exercised. The plain-comment approval/merge path is now verified live.
- Signed external webhook delivery and production TLS/domain routing need verification on
  the intended public deployment; reading a GitHub comment is not proof its webhook arrived.
- Paid Claude, local Ollama, multiple-provider interpreter fallback and real native compaction
  were not exercised. Single-provider OpenAI interpretation was verified in the continuation.
- The 10–20-task completion/cost benchmark has not run. One small successful task does not
  establish feature-task success rate, model ranking or a percentage reduction in cost.
- Long-context/service-tier pricing outside the configured standard catalog is not covered
  by this small-context acceptance. Verify pricing applicability before a larger workload.
- Four low-severity frontend dependency advisories and upstream Python deprecation warnings
  remain; no automatic force-upgrade was performed.
- Operational V2 UI localization still needs complete EN/KA coverage.

## Handoff

Read [architecture and features](../PRODUCT.md), [execution/accounting logic](v2-implementation.md)
and [setup/operator requirements](initial-setup.md). The live PR is merged and the task complete.
The local approval implementation is deployed but remains uncommitted in the working tree.
