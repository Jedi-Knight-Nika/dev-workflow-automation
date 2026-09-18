# Setup and development

[Architecture](architecture.md) · [Evaluation and results](evaluation.md)

Commands run from the repository root unless stated otherwise. Keep secrets and runtime data out of Git.

## Local setup

1. Install Docker with Compose.
2. For a new checkout, copy `.env.example` to `.env`. Do not overwrite existing configuration. Replace placeholder secrets; generate independent secrets with `openssl rand -hex 32`.
3. Keep PostgreSQL credentials synchronized with both database URLs. Configure the GitHub App identity and PEM mount when using repository integration.
4. Start the console:

```sh
sh scripts/start-local.sh --mode console
```

UI: `http://localhost:3000`. API: `http://localhost:8000/api`.

Choose `console`, `execution` or `full` explicitly. Execution adds native workers; full also adds monitoring/alerts. The shell default is **full**, not console. Execution modes can resume authorized queued work and require prepared repository images, validation commands, provider credentials, verified prices, Team enrollment, budgets and reviewer policy. Console does not stop separately running workers. `--no-build` reuses existing images and does not deploy source changes.

## Development servers

Install the prerequisites below, then run `make setup`. Use `make dev-backend` and `make dev-frontend` in separate terminals. The frontend proxies `/api` to `http://localhost:8000` unless `API_URL` overrides it.

Host-run servers need reachable development database URLs, not the Compose-only `postgres` hostname. Apply migrations with `make migrate` against that configured database. Keep scheduling off unless execution is intentionally configured.

## Code quality

Use Node.js 22.13+ (or a supported newer LTS), Python 3.12+, uv, and Rust with the `rustfmt` and `clippy` components. The desktop check also needs the platform's Tauri build dependencies. On macOS, install shell tools with `brew install shellcheck shfmt`; other platforms can use the upstream binaries or their package manager. Run `make setup` to install the locked Python and frontend dependencies. Desktop JavaScript reuses the frontend tooling; there is no second linter dependency tree.

| Files                                                                  | Tools                                                                                                          |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Python application, migrations, tests, evaluations and utility scripts | Ruff 0.16.8 for lint/format; existing mypy for application and selected operator-script types.                 |
| TypeScript, JavaScript and Svelte                                      | ESLint 10.10.0 with typescript-eslint 8.70.0 and eslint-plugin-svelte 3.23.0; svelte-check for frontend types. |
| Web code, HTML/CSS, JSON, YAML and Markdown                            | Prettier 3.9.8 with prettier-plugin-svelte 4.1.1.                                                              |
| Desktop Rust                                                           | Rust's bundled rustfmt and Clippy; CI uses Rust 1.96.0.                                                        |
| Shell scripts                                                          | ShellCheck 0.11.0 and shfmt 3.14.1.                                                                            |

Formatter/linter package releases were checked on 2026-09-18. Python/JavaScript versions are pinned and locked; Rust uses its bundled tools rather than a separate formatter package. Existing runtime/framework dependencies are not upgraded as part of formatting. Keep the shell tools aligned with the listed versions when reproducing formatting locally.

```sh
make format        # Format Python, web/config/docs, Rust and shell; no lint auto-fixes
make format-check  # Verify formatting without writing
make lint          # Python, frontend/desktop JavaScript and shell lint
make typecheck     # Existing Python and Svelte/TypeScript checks
make desktop-check # Rust Clippy + type/build checks
make check         # All of these, tests, operational syntax and frontend build
```

Prettier has one root configuration, and `.editorconfig` defines shared whitespace. Generated files, lockfiles, dependencies, local runtime data and third-party vendor assets are excluded from formatting. `make format` does not run the application, execute provider tasks or deploy anything. CI enforces formatting/linting plus the existing test/build checks; browser and live deployment acceptance remain separate.

Tool references: [Ruff](https://docs.astral.sh/ruff/), [Prettier installation/version pinning](https://prettier.io/docs/install), [Svelte ESLint support](https://sveltejs.github.io/eslint-plugin-svelte/user-guide/), and [Rust components](https://rust-lang.github.io/rustup/concepts/components.html).

### Before pushing

Unused-code checks are enforced, not advisory: Ruff rejects unused Python imports, local variables, annotations and unpacked bindings; ESLint rejects unused JavaScript/TypeScript/Svelte imports, locals and parameters, including parameters before the last used argument. In web code, intentionally unused callback parameters or caught errors can use an `_` prefix; unused imports/locals cannot hide behind that naming convention. Object-rest exclusions are allowed. Python retains Ruff's conventional underscore-prefixed dummy bindings. Stale ESLint disable comments and Ruff `noqa` suppressions are errors. ESLint permits zero warnings, Svelte checking fails on warnings (including unused CSS), and Rust Clippy already treats warnings as errors.

ESLint owns the web unused-variable policy rather than duplicating it in TypeScript compiler flags. These are local static checks, not proof that every exported function, public API or dynamically registered component is used; there is no new whole-project dead-code scanner. No automatic deletion of imports or suppression of new findings is configured.

Python keeps Ruff's default safety checks and explicitly extends them with **Pyflakes (`F`), Bugbear (`B`), import ordering (`I`), modern Python syntax (`UP`), unused unpacked bindings (`RUF059`) and stale suppressions (`RUF100`)**. This catches undefined names, mutable defaults, late-bound loop closures, unused loop variables and unchained exception raises, not just formatting. The same configuration applies to the backend, evaluations, migrations, tests and root utility scripts. The existing FastAPI route exception for dependency defaults (`B008`) remains narrowly scoped.

Mypy remains in **strict mode**, with unreachable-code checks and error-code-specific `type: ignore` required. Application functions must be typed, incompatible assignments/calls and unparameterized generics are rejected, and stale type suppressions are reported. Tests/migrations receive Ruff checks but are not newly forced through mypy. Required interface/callback parameters are not globally banned in Python. Runtime validation guards are preserved even when annotations make them look redundant; `ALL`, blanket complexity limits and broad new ignore lists are deliberately avoided. References: [Ruff rules](https://docs.astral.sh/ruff/rules/) and [mypy strict mode](https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict).

Run `make hooks` once in an existing checkout; `make setup` also installs the hook for new checkouts. This uses Git's native `core.hooksPath` and the version-controlled `.githooks/pre-push`, with no Husky or additional dependency. An existing custom hooks path is preserved: installation stops with instructions instead of replacing it.

Every normal `git push` runs `make pre-push` for the whole working tree: formatting checks, Python/web/desktop/shell lint, Python/Svelte type checks, Rust Clippy and operational syntax checks. Any failed command blocks the push. The hook does not auto-format, stage, stash or commit files. Fix formatting with `make format`, review and commit the changes, then push again.

The quality-tool prerequisites in this guide must be available in the environment that launches Git, including GUI clients. These checks inspect the current checkout, not another branch or a snapshot of outgoing commits; push the intended checked-out branch with changes committed. Full tests and builds stay in `make check` and CI, and browser/live acceptance stays separate. Local hooks can be bypassed, so required CI checks remain the enforcement boundary. See [Git's hook documentation](https://git-scm.com/docs/githooks#_pre_push).

### Tests

`make test` runs backend and frontend unit suites. Database integration tests require a migrated, isolated `TEST_DATABASE_URL`; never use operational data. `make check` also runs formatting, lint, types, operational syntax, frontend build and desktop Clippy. Browser acceptance is separate: `make frontend-e2e`. Docker and live-provider checks have independent opt-in prerequisites. Mocked tests do not prove live credentials, publication, merges or billing accuracy.

## Desktop launcher

This Tauri wrapper displays the local web console. It delegates startup to the repository's `scripts/start-local.sh`, waits for the frontend on port 3000, and displays startup errors instead of navigating to an unavailable page.

### Prerequisites

- Install Docker with Compose, Rust/Tauri platform dependencies, and Node.js.
- Configure the repository `.env` and required mounts as described in the local setup section above.
- Build the desired stack once from the repository root, for example `sh scripts/start-local.sh --mode console`. The desktop launcher uses `--no-build`; rebuild images explicitly after source changes.

### Run

From `desktop`:

```sh
npm ci
npm run tauri dev
```

Debug builds locate the repository relative to `src-tauri`. Packaged builds require `AEW_REPO_ROOT` pointing to the checkout containing `compose.yaml` and `scripts/start-local.sh`.

The desktop default is `console`, preserving its non-executing base-Compose behavior. Set `AEW_START_MODE=execution` or `AEW_START_MODE=full` in the launch environment to opt into execution or execution plus monitoring. These modes can resume authorized queued work; they still require configured runtime credentials, repository access, and spending policy. The shell script alone defaults to `full` for compatibility with its existing callers.

The launcher starts services; closing the window does not stop them. It is a local wrapper, not an installer or a production deployment manager.

## Execution and production

The Compose project runs PostgreSQL, backend, controller, frontend, provider gateway, Prometheus, cAdvisor, Node Exporter, PostgreSQL Exporter, Blackbox Exporter, and optional Alertmanager/Ollama. Developer, validator, and publisher containers are ephemeral.

`compose.yaml` is the local base. `deploy/compose.production.yaml` is the Linux/TLS base. `deploy/compose.execution.yaml` adds native execution. `deploy/compose.observability.yaml` adds monitoring; the desktop overlay adapts host collectors locally.

The native SDK base and repository-ready runner image are separate so rebuilding the base cannot erase locked repository dependencies. Production images should use verified immutable digests.

Caddy joins ingress/application networks. The controller has only required networks plus Docker authority. Ollama and monitoring are private. Backend joins monitoring only to query Prometheus. Developer runners never join it and reach providers only through restricted egress. Monitoring/Ollama/Docker ports are not published.

Operators configure one synchronous/asynchronous URL pair for the same database, secrets, GitHub App identity, absolute execution data root, runner images, harness flags, validation argv, scheduler limits, price catalog, Team budgets, source routes, reviewer/check policy, and optional monitoring tokens/retention/thresholds. Paid harnesses and scheduling default off until admission prerequisites pass.

Use `deploy/.env.example` for production configuration and `deploy/compose.production.yaml` as the Linux/TLS base. Configure DNS, Caddy operator authentication, independent secrets, verified images and private networks before enabling workloads. The execution data root must resolve to the identical absolute path on Docker host and controller. Never publish Docker, Ollama or monitoring ports.

Back up before migrations and deploy compatible API/frontend/controller images. Migration `0014_task_creation_requests` is additive; an old backend cannot honor the new atomic Team-assignment creation contract. Application rollback can leave its table in place; dropping it loses retry history and must not race new instances.

For consistent backups, stop API/controller, activity projector and every managed task runner. Read `deploy/backup.sh` and `deploy/restore.sh` before using `make backup-production` or `make restore-production`. Backup requires `CONFIRM_QUIESCENT=YES`; restore also requires `BACKUP_SET`, `CONFIRM_RESTORE=RESTORE`, a new database and empty runtime directories. Backups contain protected credentials, source and state.

Use the explicit credential-rotation utility rather than only changing `APP_SECRET_KEY`; otherwise existing encrypted records can become unreadable. Real-workflow verification is an authorized sandbox operation, not a routine health check.

Older deployments crossing the canonical-identifiers migration must reconcile published branch identities with GitHub: changing a stored name does not rename remote Git refs. A historical local review found a `template1` collation mismatch (2.36 versus 2.41); check current server state before deliberate database maintenance, not an automatic reset.

## Coordinator configuration

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

### Recovery and uncertain delivery

An interrupted model purchase is not silently repeated. An interrupted/uncertain outbound POST becomes `UNKNOWN`, visible on the task. A single automatic read-only reconciliation checks for a unique recent message from the verified integration identity. The dashboard can queue another “Check delivery” without resending. Missing history, ambiguous matches or unavailable identity leave the effect unknown. GitHub review-request uncertainty requires inspection of review history because a reviewer may already have answered or been removed. Known effect IDs and matching integration-identity echoes suppress repeat wakeups; providers without a reliable idempotent send cannot promise exactly-once network delivery. No automatic resend occurs after uncertainty. Inspect the remote conversation and usage before explicitly requesting another action. An authenticated webhook confirmation wins over a later network timeout. Delivery verification cannot make an uncertain purchase repeat.

Automated coverage exercises real PostgreSQL migration/reflection, dedupe/coalescing, shadow behavior, clarification and resume, current-revision rejection, no retry after unknown delivery, multi-controller global capacity/fairness, periodic reservations, provider destination contracts and codec round-trips. These checks use mocked model/provider responses. Real provider permission smoke tests and paid model quality comparisons remain rollout validation; no external-service result is inferred from mocks. Docker runtime, backup/restore and authenticated proxy acceptance are tested separately without inference.

Feedback arriving during a paid Developer generation retains a `WAITING_ENGINEER` action. After usage settles, it is applied if its state is still current, or the original event is reconsidered against the newly completed work. This is a progress-triggered decision, not an idle paid retry. Unknown settled usage still requires reconciliation.

### Operational visibility

Prometheus now exposes retained event/run/action/human-request states, oldest pending event age, events per wake, Coordinator known cost/unknown usage, paid-slot occupancy/capacity, recent queue wait and waiting-Team count. Metrics reuse the existing 15-second cached scrape projection and contain no task IDs or message bodies in labels. Unknown costs remain separately visible instead of becoming zero-cost successes. Operator action assessments in the task activity drawer record the latest CORRECT/INCORRECT label per action; incorrect-action rate uses only labeled actions. Additional metrics cover clarification, explicit operator overrides, accepted terminal tasks, first full-validation batch pass rate, repair requests, manual takeover, time to PR/merge, and total terminal-workflow cost/tokens per accepted delivery. Unobserved rates are NaN, not fabricated zeroes; validation coverage is exposed because historical batch outcomes are not inferred from targeted checks.

GitHub review requests are restricted to one to ten configured immutable human reviewer IDs; the current open, non-draft PR head is refreshed before the request. Existing requested reviewers are not requested again. Slack actor permissions are checked against the task's exact workspace/channel route.

## Activity replay configuration

Normal Compose builds include a separate `activity` service. Production and execution overlays include it too. The API image already contains Git; no additional package or service is required. Compose waits for the API migration/health check before starting projection. When running processes directly, apply the normal migrations and run `python -m app.activity_runner` from `backend` alongside the API.

| Setting                        | Default | Purpose                                                                                    |
| ------------------------------ | ------- | ------------------------------------------------------------------------------------------ |
| `ACTIVITY_ENABLED`             | `true`  | Enables API access and the projector loop                                                  |
| `ACTIVITY_COLLECT_FILES`       | `true`  | Enables validated-commit metadata collection                                               |
| `ACTIVITY_FILE_RETENTION_DAYS` | `0`     | Zero preserves file detail; positive values expire old derived file rows in batches of 100 |
| `ACTIVITY_POLL_SECONDS`        | `5`     | Delay between projection batches                                                           |
| `ACTIVITY_MAX_EVENTS`          | `5000`  | Maximum events loaded into one viewer                                                      |
| `ACTIVITY_MAX_FILES`           | `5000`  | Maximum file-change rows loaded into one viewer                                            |
| `ACTIVITY_MAX_TASKS`           | `200`   | Maximum tasks in one viewer                                                                |
| `ACTIVITY_MAX_REPLAY_DAYS`     | `90`    | Maximum requested historical range                                                         |

Set `ACTIVITY_ENABLED=false` for both API and projector to disable the module; existing engineering processing remains functional. The launcher reports that visualization is disabled if opened. No render worker or visualization request is created merely by visiting the dashboard.

The projector has a 256 MiB/0.25 CPU Compose limit, a two-connection pool, no pool overflow, bounded SQL/lock waits, no Docker socket, and no provider credentials. Its workspace mount is read-only. The API uses a separate two-connection activity pool. This isolates the execution path, but projection and viewing still consume finite database/browser resources. Larger installations should measure query latency before increasing limits; oversized ranges offer a UTC hourly/daily summary without loading raw events or starting a renderer. The aggregate query returns at most 366 daily or 169 hourly buckets within the configured time range, shares the frozen sequence and scope rules, and retains the two-second SQL timeout. Selecting a bucket narrows the replay range. Aggregates provide event/task/validation/review/response counts; precise lifecycle duration and receipt analysis remains in bounded replay.

Stop the activity service along with other writers during an operationally quiescent backup/restore. The new tables are included in normal database backups. Rebuilding them is possible from retained source records, but purging history is an operator maintenance action and is not part of normal startup. Missing file history cannot be recreated after its workspace/commit has been removed.

### Viewer monitoring

The existing Prometheus endpoint exports activity query latency/errors, returned event counts, active/resumed SSE streams, and projector lag refreshed at scrape time (-1 when unavailable). Browser reports include first-frame initialization time, measured Canvas frame processing/drawing time, redraw counts, reconnects, worker crashes, graphics/Gource failures, and observed session duration. Rendering is event-driven; these are actual redraw measurements, not a claimed continuous FPS rate. Reports are bounded numeric deltas with no task IDs, messages, or arbitrary labels. Best-effort delivery failures never interrupt playback. Timers and streams are disposed with the viewer; no browser monitoring runs before it starts.

## Retention and performance

Host/container scraping is approximately ten seconds, application/database scraping fifteen seconds, and availability probing thirty seconds. Prometheus retention is bounded by time and disk size. Summaries, incidents, AI usage, tasks, and forecasts remain durable in PostgreSQL.

Live snapshots and aggregates use bounded caches. Historical requests are keyed by typed metric/range/step. Prometheus response size, points, concurrency, timeout, malformed data, warnings, non-finite values, and cardinality are bounded. Monitoring services have CPU, memory, and process limits.

## Troubleshooting

| Symptom                               | Inspect first                                                                                         | Do not assume                                           |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Task remains NEW                      | Team enrollment, repository grant/runtime, scheduler flag and worker presence.                        | Creating a task means coding was authorized.            |
| WAITING_HUMAN / missing configuration | Recorded event/reason, enabled profile, credential, verified pricing, budget and validation commands. | Repeated resume clicks can fix missing setup.           |
| Tokens/cost incomplete                | Run receipts, reservation and recovery evidence.                                                      | Missing usage means zero cost.                          |
| Native interruption/no progress       | Failure code, preserved workspace, checkpoint and bounded repair evidence.                            | Starting a fresh paid session is always safe.           |
| Validation failed                     | Exact commands, exit codes, timeout/output tails and candidate revision.                              | The AI's “tests pass” summary is the validation record. |
| Push/PR uncertain                     | Task branch SHA, recorded validation, external PR state and lifecycle version.                        | Database rollback can undo a remote Git operation.      |
| Review/merge waiting                  | Current PR head, checks, eligible approval and Team merge policy.                                     | A passing local check alone authorizes merge.           |
| Stale UI/replay                       | Request ID, stream state, reconciliation polling and projector lag.                                   | A missed browser event means the task did not advance.  |

Operational endpoints include `/health/live`, `/health/ready`, `/metrics` and signed `/webhooks/*`. HTTP request IDs correlate failures with logs. Readiness is not a substitute for validating a real repository runtime.

Use `make operational-check` for shell/Python utility syntax. Backup and restore tools are under `deploy`; real workflow verification is `scripts/validate_real_workflow.py`. Credential rotation, restore, retention and live-provider validation have side effects and require deliberate environment/authorization choices. A successful mock-provider test is not permission to run them against production.
