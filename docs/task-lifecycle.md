# Task lifecycle: from creation to merge

This guide describes the implemented engineering path from a task request to a merged GitHub pull request. It is a description of the current control plane, not a promise that every task will run automatically: repositories, Teams, credentials, budgets, runtime profiles, and delivery policy must be configured first.

## Who does what

- **Operator or external work source** creates or updates work and resolves human blockers.
- **Team** supplies the enabled Developer profile, repository scope, capacity, budget, and automation policy.
- **Scheduler and workers** claim durable phase jobs and run intake, development, validation, publication, review handling, and merge work.
- **Developer runtime** works in an isolated task workspace. Its output is a candidate, not merge authority.
- **Validator** runs configured deterministic commands in a separate container and may create the local commit after successful checks.
- **GitHub** hosts the pull request, reports checks and reviews, and performs the final merge request.
- **Delivery policy** decides whether a reviewed, validated pull request is eligible for automatic merge.

## Durable records and lifecycle state

PostgreSQL is the source of coordination. Tasks, Team assignments, repository scopes and dependencies hold current work state. Creation requests prevent duplicate manual creation; jobs and task events record dispatch and lifecycle evidence; native sessions and AI runs record execution; validation runs and review cycles record revision-specific evidence.

A task has three separate lifecycle fields:

- **Status** says whether it can run: `NEW`, `ACTIVE`, waiting for external or human input, `PAUSED`, `FAILED`, `CANCELLED`, or `MERGED`.
- **Stage** says where it is: `INTAKE`, optional `PLANNING`, `DEVELOPING`, `VALIDATING`, `PUBLISHING`, `REVIEWING`, `FIXING`, `MERGING`, or `COMPLETE`.
- **Wait reason** explains a stop, such as missing configuration, budget exhaustion, provider outage, approval, GitHub checks/review, merge conflict, or manual takeover.

Transitions are fixed domain rules, versioned, and persisted with lease/optimistic checks. A task cannot implicitly reopen after it is merged, cancelled, or failed. Pausing retains its stage. A requirement revision increments the requirement version and invalidates stale evidence; work then returns to intake or fixing as appropriate.

## 1. Create and authorize work

Manual creation uses `POST /api/tasks`. The request can include a title, description, repository, selected Team, metadata, an optional `start_work` intent, and a retry UUID.

`CreateTask` performs one transaction:

1. It creates the task.
2. It assigns the explicitly selected Team when provided.
3. It records a `TASK_CREATED` event.
4. When `start_work` is requested, it requests execution.
5. It stores the request UUID and a fingerprint of the request.

Repeating the same UUID with identical details returns the original task instead of creating another one. Reusing that UUID with different details is a conflict. Assignment or another error rolls back the transaction.

External work can also arrive through signed webhooks and reconciliation. Providers have their own persisted delivery and snapshot identities; manual request idempotency is not a universal webhook-deduplication mechanism. Trello is an available integration type only when configured; this guide does not assume a particular Trello board workflow.

## 2. Enroll execution and prepare the workspace

Starting work does not immediately start an unbounded model loop. Enrollment checks that the Team, repository, policy, scope, task state, Developer profile, budget, and workspace ownership permit execution. Missing or unsafe configuration produces a durable waiting state and event rather than silently starting an incomplete runner.

For an enrolled task, the system uses a task branch named `agent/task-<task UUID>` and a task-local repository workspace. Intake prepares verified directories, fetches and checks out the base branch, and records base/head evidence only if the lifecycle version is still current. It refuses to overwrite a nonempty unregistered workspace. Git credentials and remotes are not persisted in the task Git configuration.

## 3. Claim and run phases

The scheduler recovers lost leases and receipts before dispatching work. It claims phase jobs with database locks, lease tokens, expiry, capacity limits, dependency checks, Team availability, retry timing, archive state, and manual-takeover checks. The worker revalidates its lease and monitors heartbeats while a phase runs. A revoked or expired lease stops authority to continue.

The normal progression is:

```text
INTAKE → DEVELOPING → VALIDATING → PUBLISHING → REVIEWING → MERGING → COMPLETE
```

Planning is conditional. Development or review feedback may move work to `FIXING`; validation failure also moves it there. Publishing and merge rechecks wait for GitHub review. A model result alone cannot authorize publication or merge.

The Developer request contains the authoritative requirement, current feedback, repair evidence, checkpoints, and coordination changes. The isolated harness receives only the configured workspace and allowed provider environment. Native execution records sessions, runs, usage, receipts, and checkpoints. Provider, timeout, token, budget, and runtime failures are classified rather than being treated as successful work merely because files changed.

## 4. Validate and commit

Validation is deterministic and separate from Developer execution. A repository runtime profile supplies validation commands and, when configured, the validator image. Missing commands or a branch blocks the task as missing configuration.

The validator:

1. Runs in a dedicated non-root container with the expected task branch and workspace.
2. Fingerprints candidate files and runs the configured commands with timeouts and bounded output.
3. Rejects a run that changes repository files during validation.
4. When checks pass and the worktree is dirty, stages the changes and creates the local commit with the configured Team author and publication title.
5. Returns the exact HEAD SHA, fingerprint, command results, and change summary.

The system persists validation evidence against the task's current requirement version and revision. If validation fails, or review detects changes that require attention, the task returns to fixing. Two repeated failures without workspace progress stop automated paid turns and require inspection instead of retrying indefinitely.

## 5. Publish and review the pull request

After successful validation, the task advances to publishing. Publication creates or updates the GitHub pull request for the task branch; the task then enters `REVIEWING` and waits externally for GitHub review.

GitHub events, polling, and reconciliation provide review and check information. New review feedback can move the task to `FIXING`, where another development and validation cycle produces fresh evidence. Requirement changes likewise invalidate prior evidence. Review handling is external-state aware: a GitHub response, a delayed webhook, or a polling result is not replaced by a model judgment.

A human blocker, such as approval required or missing requirement detail, leaves the task in a durable waiting state. An operator may pause, cancel, take over, revise, resume, or explicitly release a takeover. A manual takeover keeps the task paused until explicitly released.

## 6. Authorize and perform merge

A task can advance from review to merging only through delivery-policy authorization. Before calling GitHub's merge API, the merge phase locks the task and job and rechecks the lease, lifecycle version, Team, repository, published PR number, current revision, and runnable state.

The merge gate requires all of the following for the current head SHA:

- Team auto-merge is enabled.
- The repository is enabled, unarchived, and allowed by the Team policy.
- The PR is open and its head matches the task's expected revision.
- Persisted validation passed for that revision and requirement version.
- Required GitHub checks are complete and passing.
- There is no blocking review and no pending review message.
- GitHub confirms the PR is mergeable.
- The task is active in `MERGING`, not archived or under manual takeover, and its Team is enabled and not paused.
- Approval evidence exists, is for the current head, and comes from an authorized reviewer. If policy requires formal approval, informal evidence is not enough.

Any failed condition produces a merge recheck and returns the task to review rather than merging. If GitHub already reports the same head as merged, the system reconciles that result instead of submitting a second mutation. Otherwise it submits the merge, records confirmation evidence and the merge SHA, updates repository state, and transitions the task to `MERGED` / `COMPLETE`.

## Failure, recovery, and visibility

Failures are not silently converted into progress. Configuration, budget, token, provider, runtime, integration, approval, review/check, and conflict problems are represented by waiting or blocked lifecycle state and task events. Terminal tasks do not reopen automatically.

Jobs use expiring, token-fenced leases so a stale worker cannot finish another worker's claim. Lifecycle changes also create durable activity notifications in the same database transaction. RabbitMQ distributes those notifications for activity projection, while periodic reconciliation catches up after broker outages or missed messages. These notifications do not authorize model execution, publication, or merging.

The UI and history APIs can show task events, phase runs, native runs, validation results, review cycles, and current lifecycle state. They are operational evidence; the database state, valid lease, deterministic validation, delivery policy, and GitHub evidence remain the authority for advancing work.

## Configuration-dependent boundaries

This repository implements the control flow and guards described above. Actual execution requires enabled Teams, repositories, integration credentials, provider access, budgets, validation commands, and scheduler workers. GitHub's own branch protections, checks, permissions, and availability remain external constraints. If auto-merge or approval policy is not satisfied, the system waits or rechecks; it does not bypass GitHub or human review.
