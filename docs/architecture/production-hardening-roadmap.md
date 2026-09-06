# Production Hardening Roadmap

This document tracks the remaining architecture work required before scaling the orchestrator
beyond its current local/small-team operating model. Authentication is intentionally out of scope
for now. Each change must preserve existing behavior until its replacement is validated.

## Engineering rules

- Keep domain decisions separate from infrastructure side effects.
- Prefer additive migrations and backward-compatible API changes.
- Introduce concurrency only after shared resources have correct locking.
- Every new limit must fail safely and create an actionable, audited state.
- Do not replace deterministic behavior with model output.
- Land focused changes with tests; do not combine unrelated redesigns.

## Ordered implementation plan

### P0 — Correctness and product integrity

1. **Graph-driven workflow routing** — `COMPLETED`
   - Make the task-pinned workflow revision authoritative for post-job routing.
   - Keep the existing completion policy as a compatibility fallback for tasks without a complete
     graph route.
   - Validate source outcomes, target capabilities, loop limits, and system destinations.
   - Persist every matched edge and fallback decision.

2. **Linear cursor pagination** — `COMPLETED`
   - Follow GraphQL `pageInfo.hasNextPage/endCursor` for issues, members, and workflow states.
   - Preserve current result mapping and sorting.
   - Add multi-page adapter tests.

3. **Repository/worktree locking** — `COMPLETED`
   - Serialize shared cache fetch and worktree registration per repository.
   - Allow different repositories to prepare concurrently.
   - Use a cross-process lock in hosted mode and a portable local fallback.

4. **Workspace cleanup and retention** — `COMPLETED`
   - Define retention by terminal task state and last activity.
   - Never delete an active, leased, manually controlled, or dirty workspace silently.
   - Remove registered Git worktrees correctly before deleting files.

5. **Task archival** — `COMPLETED`
   - Replace destructive task deletion with archival for normal product operations.
   - Keep jobs, events, findings, checkpoints, approvals, and routing history queryable.

### P1 — Safety and cost control

6. **Terminal ownership for multiple replicas** — `COMPLETED`
   - Persist runtime ownership/heartbeat and route reconnects to the owning worker.
   - Ensure expiry, close, replacement, and worker shutdown terminate the PTY.
   - Do not claim multi-replica safety while using process-local runtime state.

7. **Spending circuit breakers** — `COMPLETED`
   - Support per-job, per-task, and per-team configurable USD/token limits.
   - Check the budget before provider calls and bounded retries.
   - Route exhausted budgets to `NEEDS_HUMAN` with an incident, never an infinite retry.

8. **Provider gateway efficiency** — `COMPLETED`
   - Reuse pooled HTTP clients.
   - Retry only transient 429/5xx failures with bounded jittered backoff.
   - Add provider-supported prompt caching behind provider-neutral request metadata.
   - Replace repeated full-repository executor context with delta/on-demand context.

### P2 — Data and read scalability

9. **Indexed agent-knowledge embeddings** — `COMPLETED`
   - Migrate text embeddings to the existing pgvector representation.
   - Backfill safely and add an HNSW/IVFFlat index appropriate to dataset size.
   - Remove Python/full-scan similarity fallback after parity tests.

10. **Dashboard/team query consolidation** — `COMPLETED`
    - Replace remaining list-then-query-per-item patterns with grouped aggregates.
    - Replace day-by-day history queries with one grouped date query.
    - Add query-count regression coverage where practical.

11. **Bounded scheduler concurrency** — `COMPLETED`
    - Start only after repository locks and workspace leases are proven.
    - Use a configurable semaphore and preserve team concurrency limits.
    - Keep job claiming in PostgreSQL; add push wake-up only if polling latency becomes material.

## Already completed from the audit

- Job claiming is transactionally serialized for the team concurrency check.
- Review cycle limits escalate instead of looping forever.
- Task/team and tool-event hot-path indexes exist.
- Workflow revisions are snapshotted.
- Command policy detects forbidden operations hidden behind interpreters.
- Approval resolution is row-locked.
- Terminal close terminates the local PTY and terminal tokens are absent from URLs.
- PR publication recovers an already-created branch PR after partial failure.
- GitHub repository discovery follows pagination.
- Provider calls reuse HTTP clients, retry bounded transient failures, and support Anthropic prompt
  caching.
- Returning executors receive repository deltas instead of the complete repository snapshot.
- Agent knowledge is stored as `vector(1536)` with an IVFFlat cosine index; the SQLAlchemy text
  annotation is only a compatibility representation and queries use vector operators in PostgreSQL.
- Team, role, agent, dashboard, and history reads use grouped/batched queries rather than per-item
  query loops.
- Pinned workflow edges now drive Intake, Thinker, Executor, Tester, and Reviewer completion;
  legacy tasks retain compatibility routing and delivery remains a deterministic publication gate.

## Deferred explicitly

- User authentication and multi-tenant authorization.
- Event sourcing, Kafka, Redis, or a generalized distributed workflow engine.
- Drag-and-drop workflow editor redesign; runtime correctness comes first.
