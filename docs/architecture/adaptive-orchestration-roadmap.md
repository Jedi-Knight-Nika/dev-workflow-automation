# Adaptive orchestration roadmap

The workflow graph remains the sole authority for routing. Adaptive orchestration selects
an execution strategy, budgets, and validation requirements within that graph; it does not
create a second routing engine.

## Implementation order

1. **Task profile and execution strategy** — classify complexity, risk, uncertainty,
   parallelizability, and tool density with deterministic rules. Persist the profile,
   reasons, chosen strategy, and strategy version on the Task.
2. **Budgets and measurable progress** — attach bounded Job/route budgets and compare
   repository SHA, changed-files hash, test failures, findings, plan revision, and result.
   Repeated identical state becomes `NO_PROGRESS`; model prose is not evidence.
3. **Failure classification** — distinguish infrastructure, provider, protocol, tool,
   implementation, validation, architecture, policy, security, and external-wait failures.
   Infrastructure and policy failures must not consume implementation-rework cycles.
4. **SHA-bound validation gate** — accept validation/review evidence only for the exact
   repository revision and validation configuration. Any new commit invalidates readiness.
5. **Deterministic Tester fast path** — execute configured checks without an AI call for
   low-risk tasks. Invoke the AI Tester for failures, ambiguity, missing evidence, or
   elevated-risk policy.
6. **Provider/integration circuit breakers and eval telemetry** — build on existing retry,
   cost, and trace data before adding parallel specialists.

## Deferred deliberately

- Parallel specialist fan-out, until task telemetry proves independent workstreams exist.
- ML-based task classification; rules remain explainable and versioned for MVP.
- Free-form agent delegation or peer chat.

## Invariants

- One workflow graph controls routing.
- One writer owns a task worktree.
- Budgets and permissions are enforced outside the model.
- A pass is valid only for its repository SHA and validation configuration.
- No-progress retries escalate instead of looping.
- External waits do not keep an AI worker alive.
