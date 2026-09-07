# Token efficiency and execution budgets

Implemented September 7, 2026.

## Problem and implementation plan

The reported task consumed 5,362,404 input tokens over 125 model attempts, including
78 Thinker attempts. These are historical application records, not an invoice.
Code inspection identified unlimited default token budgets, repeated full tool-history
transmission, no reserved final-answer turn, and accumulated paraphrases of plan constraints.

Completed work:

1. Enable finite job/task token and model-call defaults; check lifetime usage before
   retrieval and before model calls, including responses not yet persisted.
2. Reserve the last tool-loop call for structured output and reduce default schema repair.
3. Avoid repeated successful source reads and stop repetitive inspection.
4. Replace accumulated planning constraints with the latest complete plan and compact
   legacy memory at read time while retaining original checkpoints.
5. Reuse a validated plan only when its material inputs and clean checkout revisions match.
6. Wire limits through Compose and isolated Docker workers, add regression tests, and
   document operational limits without claiming unmeasured billing savings.

## Defaults

| Setting | Default | Scope |
| --- | ---: | --- |
| `MAX_JOB_TOKENS` | 120,000 | Recorded input + output, plus current pending responses |
| `MAX_TASK_TOKENS` | 400,000 | All jobs for the same task, including prior reopens |
| `MAX_JOB_MODEL_CALLS` | 8 | Completed response records + pending responses for a job |
| `MAX_TASK_MODEL_CALLS` | 32 | Completed response records + pending responses for a task |
| `structured_output_retries` | 1 | One schema repair after an invalid response; explicit agent configuration can override |
| Native source-read allowance | At most 100,000 bytes | A worker job's native repository tools; smaller configured context limits take precedence |

The effective per-run call allowance is the minimum of the execution strategy, agent
configuration, and global job-call limit. The job/task count checks also include
previous attempts persisted in `worker_runs`, so a scheduler retry does not reset them.
Unknown token usage still counts as a completed model call. HTTP failures that produce
no model response are governed by the existing provider retry/circuit-breaker system.

Token limits of zero explicitly disable that token limit. Call limits must be positive.
Team token/cost limits and job/task dollar limits remain separately configurable.
Dollar enforcement needs model pricing; null cost is not evidence of free execution.
The finite token/call defaults operate even when pricing is unavailable.

The settings are passed to backend, scheduler, and isolated Docker workers. Change
the environment and recreate those services to change limits. Existing task usage is
retained: the historical multi-million-token task will stop before another provider
call with these defaults. Reopen does not grant it a new budget.

## Repository inspection and final answers

Executor also supports [direct workspace editing and validation](executor-workspace-tools.md):
failed edits and checks return to the same model loop for correction, rather than
requiring another planning cycle. This retains existing spending limits.

Native tool results remain in the provider conversation so source evidence stays available.
A successful file read is returned once per conversation. A repeated request receives
`ALREADY_READ` referencing the previous full output, without consuming its bytes again.
Two consecutive read calls requesting only already-read files end further inspection.
New provider conversations clear this read-history tracking; they never refer to evidence
that was discarded. Source-byte and tool-call budgets remain bounded across context rounds.

The last permitted model call disables additional tool calls while retaining the tool
definitions, call/output pairs, and reasoning continuation. The agent must return its
structured result, or precisely identify missing evidence. This does not authorize it
to invent code or report unverified success.

OpenAI's `tool_choice: none` behavior is documented in the
[Responses API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).
The OpenAI Docs skill informed this API change. No server-side conversation storage was enabled.

Schema repair keeps the original task context and reports field errors without embedding
Pydantic's entire invalid input in each error. The previous response excerpt is capped
at 8,000 characters. Repair calls use the same job/task budget and cannot initiate more
repository inspection. The call-count check also applies to providers without native tools.

## Memory and plan reuse

A successful complete Thinker plan replaces the current plan-derived constraints and
target paths. Old checkpoints remain available for audit. For existing bloated memory,
the compiler derives these fields from the latest stored complete plan without deleting
the stored historical data. Failed planning outcomes do not replace a valid plan's constraints.

Plan fingerprints cover compiled task context, conversation, relevant memory, model,
system prompt, runtime configuration, workflow version/node, repository identities, and
actual checked-out HEADs. Operational job IDs, task state, memory version/plan pointer,
and the previous-role checkpoint do not change the fingerprint.

Only clean checkouts qualify: staged changes, unstaged changes, and untracked files
disable reuse. New context, feedback, model changes, repository commits, or configuration
changes invalidate it. Legacy plans without a fingerprint are not replayed automatically.
When inputs match, the worker checkpoints the reused `PLAN_READY` result with
`reused_plan: true`, creates no model attempt, and returns it through normal graph routing.
This is conservative: changing conversation or retrieval results can cause a cache miss.
Context compilation still runs before comparing fingerprints and can perform retrieval.

## RAG and billing boundaries

Repository RAG remains available. Current indexing already compares revisions and reuses
unchanged chunk embeddings on incremental updates. `knowledge_chunks` stores repository
knowledge; `agent_knowledge_chunks` serves separate agent knowledge. An empty latter table
alone is not a repository-indexing defect.

These changes do not claim embeddings are free or disable them. Standalone indexing and
embedding-query usage are not included in `worker_runs` token budgets. The early task-budget
check prevents a task already over budget from triggering context compilation/retrieval.
Provider billing remains the authority for dollars. Compare dashboard and task totals over
the same date range and scope; all-time SQL totals need not equal today's dashboard.

## Limits and validation

Budgets are checked between calls, so the last in-flight response can take token usage
over a threshold. Concurrent jobs can also pass a task/team check before either records
its response: this is not an atomic dollar reservation or an exact billing ceiling.
Missing usage and embedding costs are additional reasons not to claim an exact dollar cap.
Finite model-call limits provide a second stop when token usage is missing.

Tests use fake providers and temporary checkouts; no paid end-to-end AI run is needed.
Regression coverage includes final-turn source preservation, zero calls at a zero remaining
allowance, duplicate file reads, retained byte/call limits, legacy-memory compaction,
material plan-cache invalidation, dirty checkout rejection, pending/cumulative budgets,
and missing-usage call limits. Backend type, lint, and architecture checks also apply.

Validation on September 7: 383 backend tests passed, 15 opt-in database integration tests
were skipped, and backend Ruff/mypy checks passed (302 application source files).
Backend and worker images were rebuilt and recreated. The effective settings were read
inside the running worker and matched the defaults above. A read-only check of the costly
task's latest job returned `Job model-call budget exhausted (16/8)` without a provider call.
No task was reopened and no paid AI run was launched for this verification.

For a controlled live test, use one genuinely new bounded task within its budget and watch
its model attempts and input/output totals. A budget stop requires investigating the cause
or deliberately raising the configured allowance; repeatedly reopening the same task will
not bypass it. Historical usage records and provider charges cannot be undone by optimization.
