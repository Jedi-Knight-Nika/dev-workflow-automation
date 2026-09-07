# Agent efficiency: research, role design, and implementation

September 7, 2026 · Engineering Worker maintainers

## Conclusion

The previous optimization reduced Planner input but did not establish good planning
or useful execution. The latest run still spent its available turns discovering
paths, then flooded Executor context with source. The correction is to reduce
avoidable discovery and allow useful work per turn, not merely increase limits.

This implementation changes shared runtime behavior and each active role's context
or instructions. It does not switch models, remove review, increase spending limits,
delete history, or launch paid acceptance runs. The OpenAI Docs skill guided the
official-source research.

## What the latest run actually showed

Task `3e17caa9-ef28-476d-8c48-d4e1847bed49`, September 7, 16:32–16:35 Tbilisi:

| Stage | Observed behavior | Interpretation |
| --- | --- | --- |
| Deliverer | One response; 27,425 input tokens | Too much context for routing in a one-repository team. |
| Thinker | Eight responses; 45,067 input tokens; four listings, three searches, then a plan | Smaller than the prior 135,214-input planning job, but no focused source-range reads. `PLAN_READY` is not proof of plan quality. |
| Executor | Seven responses; five listings, a whole-file batch, then search | Approximately 95 KB of source was returned at once; next input grew to 39,348 tokens. |
| Outcome | Executor total 123,440 tokens exceeded its 120,000-token limit | No edits, tests, or PR; clean workspace confirmed. |

The task's 365,201-token dashboard total includes earlier attempts; this cycle added
199,751 input-plus-output tokens. These are application usage records, not an invoice.
The new trace metadata establishes the tool sequence, but does not retain raw tool
arguments or private reasoning. Consequently the exact search queries are unknown.

## Research and decisions

Official sources were accessed September 7, 2026; page publication dates were not
established. These are provider guidance, not measured savings for this application.

1. **Reduce unnecessary requests as well as context.** OpenAI recommends filtering
   irrelevant context, combining suitable steps, and using ordinary code where model
   reasoning is unnecessary. Application: resolve candidate paths from the current
   checkout in code, and avoid source retrieval for single-repository routing.
   [Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization).
2. **Make tool contracts match the operating instructions.** OpenAI documents that
   `parallel_tool_calls: false` restricts a response to zero or one tool call. Our
   prompt requested batching while that flag disabled it. Application: permit multiple
   tool calls in native worker responses, execute them sequentially through the existing
   policy/cancellation checks, and return every executed result. Independent work can
   share a turn; actions depending on an earlier result should wait for another turn.
   [Function calling](https://developers.openai.com/api/docs/guides/function-calling).
3. **Keep specialists narrowly responsible.** Handoffs are useful when ownership or
   tools/policy genuinely differ; extra specialists can add overhead. Application:
   retain the configured workflow and its review boundaries, but give each role a
   concise operating protocol. Do not add an AI coordinator to routine scheduling.
   [Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration).
4. **Cache reuse is valuable, not a substitute for small context.** Shared prefixes
   can reuse provider work, but altered prefixes break reuse. Application: preserve
   the existing stable instructions/history and cache telemetry. Total token guards
   still count cached input; this change does not invent cache-adjusted dollar totals.
   [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
5. **Compaction is a separate design choice.** The Responses API supports server-side
   compaction and requires carrying its output state correctly. Deferred here: blindly
   dropping old source or reasoning would damage exact edits and reproducibility.
   First prevent oversized reads and unnecessary turns. Provider compaction needs its
   own compatibility, state-retention and live quality evaluation.
   [Compaction](https://developers.openai.com/api/docs/guides/compaction).
6. **Measure correctness, not just a lower counter.** Evaluate individual workflow
   steps and the end-to-end outcome using representative cases. Application: add
   regressions for the observed failures and a scripted multi-file edit/test loop;
   separately require a paid acceptance run before claiming production savings.
   [Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

Research stopped after resolving the consequential API and architecture questions.
No model-price comparison or model upgrade was necessary; those would not resolve
the observed discovery loop. A guessed orchestration URL returned 404; the canonical
page linked from official documentation was subsequently opened and used above.

## Changes by role

| Role | Implemented change | Preserved responsibility |
| --- | --- | --- |
| Thinker / Planner | Current-checkout source map, bounded discovery pages, shared batched reads, concise evidence-first planning instructions | Inspect representative contracts; do not infer plan quality from a file listing or invent APIs. |
| Executor | Source map and dirty-workspace status; no automatic repository RAG for native tools; no generation of unused bulk source context; batched tool responses; bounded reads including new files | Read, edit, test, correct within the existing persistent workspace. Final validation remains independent. |
| Deliverer | No repository semantic search when there is only one candidate; multi-repository routing retrieval reduced to 2/4/6 chunks for low/normal/deep, each at most 1,200 characters | Interpret events, choose scope, and perform only authorized PR delivery actions. Manual/global knowledge remains available. |
| Reviewer | Diff/findings-first instructions; native single-repository review skips redundant repository RAG | Findings and surrounding-source inspection remain available. Missing evidence is not approval. |
| Tester | All check outcomes retained, with successful output shortened to 200 characters and failures to their last 2,000 characters | Distinguish test failure, environment failure and incomplete validation. No automatic pass for missing tests. |
| Legacy Intake | Concise classification protocol is defined for compatibility; no new Intake stage is introduced | The current runtime routes intake through Deliverer. Historical Intake usage is not evidence of a new call. |
| Scheduler/orchestrator | No new model calls or graph changes | Existing deterministic scheduling and configured workflow routing remain intact. |

The source map contains up to 40 relevant tracked paths within a 4 KB path allowance,
plus at most 15 build/instruction entrypoint paths. Explicit paths in context rank
first; other relevance is a lexical heuristic. Paths are current, but their inferred
relevance is not a substitute for reading source. Multi-repository prefixes are
included in the surrounding repository descriptor.

Native Executor previously generated seed-file context and then discarded `files`
before sending the prompt. The new compiler avoids that wasted local work as well as
removing its separate repository RAG payload. It would be inaccurate to count the
discarded seed files as previously billed input.

## Shared execution changes

- Whole-file reads and batched repository ranges share an **8,000-byte source limit
  per call**. Repository reads within a model response also share a **12,000-byte
  allowance**; cumulative source limits remain unchanged. JSON metadata is additional.
- Large source reads retain explicit limit/continuation information. Workspace-file
  reads accept line bounds, so newly created, untracked files are also inspectable
  in sections. Source exhaustion no longer disables editing/testing of already-read
  code; model-call, tool-call and spend limits still apply.
- Listing pages contain at most 40 paths and 3 KB of path text, with a continuation
  offset and guidance. A path from `source_map` no longer needs a prerequisite listing.
- Multiple tool calls are executed in order, never as concurrent workspace writes.
  A call beyond the existing tool allowance returns `NOT_EXECUTED`. Permission checks,
  approval stops and cancellation still run before operations.
- A pre-request reserve accounts for system text, task prompt, schemas, tool history,
  provider-overhead allowance, and maximum output. If it cannot fit remaining job/task
  limits, the call is not sent. Actual usage remains authoritative.
- **The reserve is a heuristic, not exact tokenization or a hard billing guarantee.**
  It uses UTF-8 bytes divided by three, plus 1,024 overhead tokens and the configured
  output allowance. It can overestimate or underestimate, especially with unusual
  content or opaque reasoning. It neither reserves dollars nor atomically allocates
  shared budgets across concurrent jobs. Existing dollar checks remain unchanged.
- Plan fingerprints now include the role-efficiency protocol and tool-protocol version,
  preventing reuse across those instruction changes. This does not broaden plan reuse.

## Verification and limitations

- Full backend suite: **412 passed, 15 skipped**. Live database integration tests were
  not enabled. Mypy passed for 304 source files.
- Backend and worker images were rebuilt and recreated; backend health passed.
  **27 focused tests passed inside the deployed worker.** Frontend remains running;
  no frontend rebuild was needed for these backend-only changes.
- Post-deployment database checks found no queued/running jobs and unchanged usage:
  Git identity 25 responses / 365,201 total tokens; estimation one response / 18,422
  total tokens. Both tasks remain `NEEDS_HUMAN`; no paid model call was triggered.
- New tests cover current-path selection, no bulk-source generation for native
  Executor, no embedding retrieval for one-repository routing, bounded whole-file and
  range batches, new-file range reads, compact check evidence, and preflight rejection.
- A scripted provider performs two reads in one response, two edits in the next,
  a real subprocess assertion next, and a final structured result: four model-loop
  turns and five operations. The test invokes no AI API and does not prove a live
  model will choose equally efficient calls.
- Real Planner quality, feature completion and dollar savings remain **unmeasured
  for this rollout**. The original Git-identity feature is not implemented by these
  infrastructure changes. Manual/global knowledge, custom role instructions and
  unusually large diffs can still increase input size.
- No historical task budgets are reset. The Git-identity task already has 365,201
  total tokens against the existing 400,000-token task default; blindly reopening it
  is not a clean acceptance test and may stop on its remaining lifetime budget.

For the next separately authorized acceptance run, use one small representative task
with sufficient remaining allowance. Track paths inspected, first edit, correction
success, actual tests, PR evidence, wall time, input/output, cache usage and total calls.
Reject the rollout as insufficient if the model only lists files or produces an
unsupported plan—even if the token count is lower. Do not repeatedly resume a failure.
