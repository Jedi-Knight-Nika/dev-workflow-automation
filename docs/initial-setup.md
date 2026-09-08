# Fresh installation and operator setup

## Database initialization

Use a new empty PostgreSQL database. API startup runs `alembic upgrade head` before serving requests.

The only revision is `backend/migrations/versions/0001_initial.py`. It applies frozen `initial_schema.sql` and `initial_entities.sql` snapshots. The schema contains the 24 current application tables listed in [PRODUCT.md](../PRODUCT.md). Existing incompatible tables/revisions are refused, not silently dropped or stamped.

Initial entities:

- One enabled Default team, with paid execution not enrolled.
- Four fixed profiles: Interpreter and Developer defaults, Thinker/Reviewer disabled.
- No role has an authorized hard spending limit yet.
- A disabled enrollment/auto-merge policy with no granted repositories.
- Disconnected GitHub, Trello, Linear, Slack, OpenAI, Anthropic and DeepSeek integration records.
- General display settings; no prices, tasks, jobs, credentials or paid runs.

To initialize a host-managed database, configure both database URLs and run:

```sh
cd backend
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run alembic current
```

Do not use stamp to bypass a schema error. No application database was reset as part of the code refactor.

## Local API/UI

Copy `.env.example` to your own ignored `.env`, set independent random secrets and database credentials, then:

```sh
docker compose up --build postgres backend frontend
```

Local ports bind to 127.0.0.1:3000 and 127.0.0.1:8000. Scheduling stays disabled. Source/provider credentials are configured through Integrations, not committed into files.

## Production native execution

Use both production files:

```sh
docker compose --env-file deploy/.env -f deploy/compose.production.yaml -f deploy/compose.v2.yaml config -q
docker compose --env-file deploy/.env -f deploy/compose.production.yaml -f deploy/compose.v2.yaml build backend worker frontend developer-image provider-egress
```

Prepare `deploy/.env` from its example. Set:

- Domain, independent application/webhook secrets and database credentials.
- OPERATOR_USER and a Caddy bcrypt OPERATOR_PASSWORD_HASH. Console/API access is authenticated at the TLS proxy; signed webhook endpoints remain reachable.
- V2_DATA_ROOT: an absolute path that is identical on the Docker host and controller. Create workspaces, native and control subdirectories there.
- A tested V2_RUNNER_IMAGE containing the target repository's build/test tools and preinstalled dependencies.
- Provider harness enable flags and the internal provider-egress network/proxy.
- Repository-specific V2_VALIDATION_COMMANDS: JSON mapping repository UUIDs to argv arrays.
- Keep V2_SCHEDULER_ENABLED=false while configuring and inspecting everything.

The API has no Docker socket. Only the trusted controller mounts it. Native children never receive the socket, database credentials or GitHub credentials. The provider gateway restricts destinations; the Developer network is internal. Validation has no network.

A stock runner cannot test every repository without dependency preparation. Build a project-specific dependency image; do not grant validation internet or production credentials to hide missing dependencies.

## Team admission checklist

1. Configure GitHub and import the exact repository. Confirm its default branch.
2. Configure a supported native Developer harness/provider/model and explicit hard USD allowance.
3. For OpenAI and cloud interpretation, register current verified pricing and source/effective date in the pricing UI. Do not copy guessed rates.
4. Set the Team's allowed repository UUIDs, task budget and cumulative Team budget.
5. Enable enrollment for that scope; leave auto-merge off for the first smoke test.
6. Configure required CI check names and authorized immutable numeric reviewer IDs before enabling auto-merge.
7. Optionally enable Thinker/Reviewer with their own limits; neither is required for routine tasks.
8. Validate the dependency image, native start/resume and offline test command first.
9. Explicitly enable the scheduler and start one low-risk task.

There is no hard-coded success guarantee for an arbitrary task or insufficient allowance. Scope and dependencies must be feasible. Task/Team/role limits all apply; increasing one does not reset accumulated use.

## Source routing

Trello integration configuration selects board/list eligibility and repository. Linear uses explicit assignee/source-state eligibility. Configure their source status destination IDs if tracker synchronization is desired. Authorized tracker-comment actor IDs live in integration configuration `v2_actor_ids`.

Slack is configured through deployment secrets/routes, not a generic credential form:

```json
{"workspace-id:channel-id":{"team_id":"UUID","repository_id":"UUID","actor_ids":"U123,U456"}}
```

Set SLACK_SIGNING_SECRET and SLACK_TEAM_ROUTES. Send `task <requirement>` (or mention the app then task) in that channel. Thread replies attach to the existing ticket. This is the Events API, not an interactive slash-command endpoint.

For GitHub issues, set GITHUB_ISSUE_ROUTES:

```json
{"owner/repository":{"team_id":"UUID","trigger_label":"engineering","actor_ids":"12345,67890"}}
```

Only open, labeled issues from configured actors are admitted; redelivery is deduplicated. Missing configuration leaves a visible ticket wait without paid work. GitHub issue close cancels its nonterminal task; issue edits record a new requirement version. GitHub issue status synchronization is not inferred from Trello/Linear destinations.

For a private local interpreter, provision a verified OLLAMA_IMAGE and model before enabling LOCAL_EVENT_INTERPRETER. The overlay exposes no public Ollama port. INTERPRETER_CLOUD_MODELS is optional (at most two explicit provider/model entries) and needs credentials, pricing and admission budget.

## Stop, resume and explicit session changes

Use Team Stop work for a durable brake. The Team stays enabled; current tickets pause and jobs lose leases. Enable execution clears the Team brake, but paused tickets require explicit Resume work. No usage is reset.

To change a suspended task's model/harness, configure the target Developer profile, then use the ticket's Native Developer session panel with an explicit reason. Version checks and unknown-cost checks apply. Same-harness compatible changes can retain the thread; cross-harness changes use a bounded handoff. The change does not run a model or resume work automatically.

## Backup and restore

Before a consistent backup, stop API/controller and all managed native/validation/Git containers. Set CONFIRM_QUIESCENT=YES only after checking them. The tools profile stores:

- PostgreSQL custom-format dump.
- workspaces, native and control directories together.
- Verified archive listings and SHA256 checksums.

The backup name includes UTC timestamp and a unique suffix. Incomplete backups remain for inspection; retention is operator-managed. These archives contain sensitive source and native state: protect/encrypt them and retain the matching APP_SECRET_KEY securely outside the archive.

Restore requires CONFIRM_RESTORE=RESTORE and CONFIRM_QUIESCENT=YES. Supply a trusted BACKUP_SET and a NEW RESTORE_DATABASE. Runtime directories must be empty. The restore tool never drops a database or deletes existing directories. Restore at the original absolute data path, preserve UID/GID ownership, verify keys and inspect suspended/unknown runs before enabling execution.

Backup/restore tooling is wired to the same native/checkouts/control tree but still requires a deployment-host smoke test.

## What must be supplied by the operator

Docker availability; a new database; protected secrets; GitHub/repository access; selected model access and verified rates; explicit Team/role allowances; a tested dependency image and validation commands; reviewer/check policy; and authorization for the first real paid run.

The refactor itself did not launch paid workers, modify the application's database, publish a PR or perform a real-model benchmark.
