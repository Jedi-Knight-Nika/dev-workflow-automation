# Token-cost research and execution recovery

Research and implementation: September 7, 2026.

Follow-up: [Role-by-role efficiency research](role-efficiency-research.md) records the
subsequent live failure and newer tool limits, batching, context selection and preflight.
Its implementation details supersede the initial rollout described below.

## Conclusion

Optimize cost per successfully completed task, not merely the maximum number of
tokens allowed before stopping. The latest live test never reached Executor, so it
did not validate the new edit–test–fix tools. Repeated database resets are not an
execution fix.

The OpenAI Docs skill guided the provider research below. Existing model choices,
spending limits, team permissions, and workflow graph are unchanged.

## Research and application

| Official guidance | Application to this app | Decision |
| --- | --- | --- |
| Reduce requests and unnecessary tokens; evaluate model choices against the work. [Cost optimization](https://developers.openai.com/api/docs/guides/cost-optimization) | Repeated planning and broad source loading incur cost without producing a patch. | Prioritize usable focused tools and shorter planning context before changing models or limits. |
| Stable reusable prefixes and cache-usage measurements support prompt-cache optimization. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) | The app retained growing tool history but discarded cache-read/write counts. Its final-answer turn changed system instructions. | Keep final-turn guidance at the end of the conversation; add stable hashed cache keys and preserve provider cache counts. |
| Compaction reduces growing conversation context while retaining useful state. [Compaction](https://developers.openai.com/api/docs/guides/compaction) | Long Executor sessions may eventually benefit, but current jobs stop after a small call allowance. | Deferred: first fix source access and measure completed runs. Do not add another summarization call to every short job. |

Caching reduces some input cost; it does not make history free or remove those tokens
from total input usage. Cache-write charges and model-specific rates also matter.
Batch/flex processing can trade turnaround time for price, but are not the first
choice for this interactive, step-by-step debugging workflow.

Separating roles is not inherently wasteful. It becomes wasteful when each role
repeats the same discovery or receives an entire accumulated history. Routine routing
should remain deterministic; planning should be reused when valid; execution should
own local correction; review should focus on changes and evidence. This change does
not remove roles or rewrite the user-configured workflow.

## Evidence from the fresh test

- Git-identity task `3e17caa9-ef28-476d-8c48-d4e1847bed49`: nine responses,
  162,763 input tokens and 2,687 output tokens. Thinker alone made eight responses,
  using 135,214 input tokens and 2,522 output tokens, ending in `NEEDS_CONTEXT`.
- Estimation task `54f30233-fcd9-4401-9ae4-aa8e2464b0e6`: one response,
  18,212 input tokens and 210 output tokens. Workspace preparation then failed
  because branch `agent/trello-vdu4nqwt` was attached to the old task's worktree.
- The Thinker events stored only aggregate streamed-character progress. They did
  not preserve the seven tool calls' arguments/results. Therefore the precise
  sequence that caused the missing-source complaint cannot be reconstructed from
  that run, and an exact historical root cause is not claimed.
- Code inspection established that whole-file reads return `CONTEXT_LIMIT` above
  file/context limits, search previously returned paths without line numbers, and
  there was no focused range reader. Planning also included broad repository
  manifests and semantic snippets even when live tools were available.

## Implemented

### Focused source access and smaller planning context

- `search_repository_snippets`: literal search within a file glob, returning up to
  20 matching lines, each bounded to 300 characters, with source paths/line numbers.
- `read_repository_ranges`: batch up to 10 ranges, at most 200 lines and 12,000
  source bytes per range, within the existing cumulative source allowance. Large
  files can be inspected in sections without raising that allowance. Files above
  1 MB remain unsupported by this reader.
- Whole-file `CONTEXT_LIMIT` results now direct the agent to range reads. A bad
  range does not discard valid results from other ranges in the same batch.
- Paths must be tracked, inside the assigned repository, and non-secret, including
  after symlink resolution. Source-reading tools do not add execution permissions.
- Native-tool Thinker context contains a small top-level repository outline rather
  than the complete manifest. It omits automatic repository semantic retrieval for
  that planning path, while retaining global/manual knowledge, task context and
  live source tools. Other roles and non-native providers retain their existing RAG
  behavior. Repository indexing itself is not disabled.
- Thinker is instructed to inspect representative contracts and execution points,
  then delegate remaining routine audits in its plan instead of demanding every
  file in full or inventing an exact migration revision.

### Recoverable worktree creation

Previously `git worktree add -B` reused a branch derived only from the external card
key. A new task ID could collide with a surviving old worktree, or reset an existing
unoccupied branch.

Workspace creation now uses `-b`, never `-B`. If the desired local branch exists,
the new task receives a branch suffixed with its full task UUID. Existing branches,
commits, and uncommitted edits are preserved. Existing workspace branches are read
back from Git and persisted, rather than guessed again from the card key.

This is isolation, not automatic recovery of old edits: a reimport starts from the
current default-branch base on a separate branch. Older work remains available for
deliberate inspection. An already-existing recovery branch is reported for inspection
instead of being overwritten.

### Observability and cache handling

- `REPOSITORY_TOOL_RESULT` task events store tool name, output size, remaining read
  allowance and bounded path/status/range metadata. They do not store file contents,
  shell arguments, query text or model reasoning.
- `PROVIDER_TOKEN_USAGE` events retain reported cache-read/write counts alongside
  input/output totals and provider response IDs. Missing fields remain unknown.
- OpenAI request cache keys hash model plus stable instructions. Final-answer
  guidance is appended as a user message instead of modifying system instructions.
- Existing dashboard totals and hard token budgets still use total input/output.
  This change does not claim cache-adjusted dollar estimates are available in the UI.

## Verification and remaining measurement

Offline regression tests cover branch collisions with dirty worktrees, preservation
of an existing unoccupied branch, a failed full-file read recovered with snippets and
ranges, secret/path rejection, reduced native planning context, and cache metadata.
Existing edit–test–fix and cancellation tests remain in the suite.

Rollout verification:

- Backend suite: **400 passed, 15 skipped**. Database integration tests were not
  enabled against the live database. Ruff checks and mypy (303 source files) passed.
- Rebuilt and started backend and worker containers; backend health check passed.
  Focused tests inside the updated worker: **22 passed**.
- Prepared the estimation task's new worktree successfully on branch
  `agent/trello-vdu4nqwt-54f30233-fcd9-4401-9ae4-aa8e2464b0e6`. The old worktree
  remains at `ecdc15b827a1065c83f01e580cc400a8bf7d88f3`, including its untracked
  `docs/estimation.md`; no old edits were copied or deleted.
- A live, non-model batch read loaded ranges from the Team model, Team schema and
  frontend Team page, consuming 3,788 source bytes from a 12,000-byte allowance.
- Both task usage totals above remained unchanged. Git identity remains `PAUSED`;
  estimation remains `NEEDS_HUMAN`. No jobs were queued or running at verification.

The next paid acceptance test should run only one task under unchanged limits. Track
completion, wall time, input/output, cache reads/writes, model calls, and every tool
status. Compare against a similar task using the same model and acceptance checks.
These offline tests prove deterministic behavior, not a percentage reduction in
real-world AI spending or guaranteed completion within eight calls.

No task usage is reset, no model is upgraded, and no automatic paid rerun is part
of this recovery rollout.
