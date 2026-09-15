# Engineering task results

Last updated: 2026-09-10. Append new results here; retain failures and corrections.

## Summary

The latest retained task completed ticket → patch → validation → PR → merge with one
Developer request and no repair. Earlier merged tasks also include interrupted attempts,
manual intervention, and platform fixes. These are development observations, not a controlled
benchmark or an overall success-rate claim.

## Reading the numbers

- **Verified** means read from local PostgreSQL on 2026-09-10: `tasks`, `ai_runs`,
  `jobs`, and, for the latest call counts, `developer_sessions.checkpoint.token_efficiency`.
  GitHub links identify PRs; their live content was not independently fetched for this log.
- Task totals include every retained AI receipt for that task, including failures and review.
- Input and output are cumulative billed-token categories. Cached input is a subset of input,
  not an additional quantity. Reasoning is not added again to output.
- Cost is USD: provider-reported cost when present, otherwise calculated receipt cost.
  This is recorded model spend, not an invoice or infrastructure/human-work cost.
- A receipt/run is not necessarily one model request. Only report request counts when
  explicit telemetry supports them. Zero-token receipts do not imply no work occurred.
- Unknown means unavailable, never zero. All four verified tasks below have zero
  unknown-cost receipts and zero recorded cache-read tokens.
- Dates below use Asia/Tbilisi (UTC+4). Recorded task SHA is the task revision, not
  necessarily the GitHub merge commit. Deployed image digest and controller commit were
  not captured for these historical trials; do not infer them from the current checkout.
- Earlier data was deleted during testing. The retained tasks are not the complete population.
  A merged status does not independently certify visual behavior or absence of human edits.

## Verified task results

### 2026-09-10 — Distinct lifecycle canvas background — PR #13

- Task: `432e7946-1cdd-4bfb-9340-2de7ddce9c3a`.
- Request summary: visually separate the Fixed engineering lifecycle canvas from the page
  background while matching the existing design.
- Outcome: **MERGED / COMPLETE**; [PR #13](https://github.com/Jedi-Knight-Nika/dev-workflow-automation/pull/13).
- Recorded task SHA: `cabd99ee55a02884c0f9a29c7d205d97b8602dd7`.
- Mode: **FAST_PATCH**. Developer: `gpt-5.6-terra`, patch harness; LOW as reported
  for the deployed fast path. Telemetry: **1 patch request, 0 repair requests**.
- Supervisor: `gpt-5.6-luna`, two completed receipts (intake and review interpretation).
- Developer: **14,559 input / 467 output**, **$0.04200000**.
- Supervisor combined: **7,739 input / 544 output**, **$0.00258725**.
- Whole task: **22,298 input / 1,011 output = 23,309 tokens**, **$0.04458725**.
- Three completed AI receipts, no failed receipts. Provider time: **16.988 seconds** total.
- All five execution jobs succeeded: preparation → Developer → validation → publication → merge.
- Preparation started 12:41:18; PR published 12:43:56; merge completed 12:46:06.
  Approximately **2m 38s to PR**, **4m 47s to merge** from preparation start.
- Achievement: successful small styling task without the old repeated coding loop.
- Caveat: no independent visual acceptance check was performed for this report; this is
  one small task, not proof of complex-task reliability or causal savings from the latest changes.

### 2026-09-10 — Improved desktop startup animation — PR #12

- Task: `896f5b83-471c-44fe-b778-889d66ec5f5b`.
- Request summary: improve the Tauri startup/loading screen with a design-consistent glow/animation.
- Outcome: **MERGED / COMPLETE**; [PR #12](https://github.com/Jedi-Knight-Nika/dev-workflow-automation/pull/12).
- Recorded task SHA: `5de73ddcffc15d0b4505b2e210c4be979e93f13b`.
- Models: Luna Supervisor; Terra patch Developer. Exact historical per-call effort/count unknown.
- Six receipts: three Supervisor, three Developer. Two Developer receipts failed
  (`PATCH_FAILED`, `CancelledError`); both record zero tokens/cost.
- Final successful Developer receipt: **4,304 input / 1,277 output**, **$0.02608250**.
- Whole task, including earlier Supervisor work: **15,897 input / 3,368 output**, **$0.03148950**.
- Created 05:40:33; terminal task update 06:06:11. This includes recovery/waiting,
  not just execution time.
- Historical incident from the conversation: localization selected oversized
  `PRODUCT_DESCRIPTION.md` for a desktop UI request. Later source-selection fixes preceded success.
- Achievement: the cheap final patch result is real, but was not a clean first-attempt task.

### 2026-09-10 — Initial desktop startup loader — PR #11

- Task: `eb380609-5549-45b8-b5bc-773e359c4ca7`.
- Request summary: replace plain startup text with an informative, animated loading screen.
- Outcome: **MERGED / COMPLETE**; [PR #11](https://github.com/Jedi-Knight-Nika/dev-workflow-automation/pull/11).
- Recorded task SHA: `3da98af777870be15855d32198f33789ec38e93b`.
- Models: Luna Supervisor; Terra patch Developer. Exact historical per-call effort/count unknown.
- Seven receipts: three Supervisor and four Developer. Developer statuses:
  FAILED (`PATCH_FAILED`) → FAILED (`PATCH_LIMIT`) → COMPLETED → FAILED (`PATCH_FAILED`).
- Only the `PATCH_LIMIT` Developer receipt records paid usage:
  **4,326 input / 2,620 output**, **$0.04225200**. Other Developer receipts record zero usage.
- Whole task: **10,243 input / 4,064 output**, **$0.04546360**.
- Created 03:17:50; terminal task update 04:26:56, including interventions/waiting.
- Conversation records frontend-only localization restrictions, a resume-without-feedback
  blocker, and patch recovery work during this task.
- Caveat: the receipt sequence alone does not explain every intervention before merge.
  Do not present this as an autonomous first-pass success or a zero-token generated patch.

### 2026-09-10 — Draggable/resizable Live Execution window — PR #10

- Task: `8c993639-8c56-4804-b01b-6704392d11d6`.
- Outcome: **MERGED / COMPLETE**; [PR #10](https://github.com/Jedi-Knight-Nika/dev-workflow-automation/pull/10).
- Recorded task SHA: `042c96af750b0afccd940600249fda49ae863509`.
- Models: Luna Supervisor; Terra patch Developer. Exact historical per-call effort/count unknown.
- Six completed receipts: four Supervisor, two Developer (initial implementation and review repair).
- Initial Developer: **10,398 input / 2,755 output**, **$0.05905350**.
- Review-repair Developer: **11,760 input / 3,640 output**, **$0.07307850**.
- Whole task: **26,047 input / 7,068 output**, **$0.13388830**.
- Created 02:25:13; terminal task update 03:14:44. Includes human review and workflow debugging.
- Conversation records a change request for minimum heights, viewport bounds, initial
  centering, keyboard resizing, duplicate CSS removal, and preserved read-only behavior.
- Achievement: initial patch plus a real PR-feedback repair reached merge.
- Caveat: all completed receipts does not mean no human intervention; informal approval
  classification needed platform fixes during this testing period.

## Older observations — conversation only, not reverified

Do not aggregate these with the verified cohort or use them as matched A/B trials.
Unknown dates, missing receipts and changing code/configuration limit comparisons.

- **Historical/log sorting:** approximately **1.43M input**, **1.36M cached input**.
  Conversation reported correct implementation with review/CI lifecycle problems.
  Exact output, final outcome and authoritative cost unavailable here.
- **Conventional commit naming:** approximately **817.6k input**, **771.6k cached**.
  Conversation reported correct implementation. Exact output/cost and final outcome unknown.
- **Early Live Execution window attempt:** approximately **709.3k input**, **679.2k cached**.
  Reported one source read; actual model-request count not verified. This does not prove
  context rot, context anxiety, or excessive file reading as the cause.
- **Two failed modal attempts:** approximately **267k / 273k Developer input**, reportedly
  12 inference cycles each, no delivery at that point. Reported issues included wrong
  interpretation (content zoom/pan instead of window drag/resize), runtime/log/formatter
  problems, and token-limit interruption. Counts are historical reports, not fresh measurements.
- **Later native modal attempt:** approximately **255k Developer input**, reportedly
  12 cycles despite an early edit. A passing/near-complete patch did not reach delivery
  before interruption. Exact retained task mapping unknown.
- **Responses modal implementation / PR #9:** reportedly approximately **205k Developer
  input**, 18 model calls, 17 tool calls and ten edits to one Svelte file. PR was created;
  later review handling reached human attention. Final task totals/outcome not reverified.

## Update checklist and next-entry template

Append after a completed or stopped trial; update an existing entry when the same task resumes.
Preserve the previous failure history and sum all retained receipts. Do not overwrite a failure
with only the final successful attempt. Use [patch evaluation](patch-evaluation.md) for replay setup.

- Date / task ID / Trello reference / PR:
- Original requirement or durable reference; short English summary:
- Starting repository SHA / final task SHA:
- Controller commit / runner image digest / relevant policy changes:
- Actual mode / model / effort, separately for planning, patch and repair:
- Patch requests / repair requests / other requests (or unknown):
- Per-role and whole-task input / cached subset / output / cost / unknown-cost count:
- Failed attempts, stop reasons, human interventions and any manual code changes:
- Targeted checks / full validation / runtime or visual acceptance evidence:
- Time to first patch / PR / merge; define whether waits are included:
- Final outcome: merged, rejected, cancelled, blocked, or still running:
- What worked / what failed / next question (avoid unsupported causal claims):
- Evidence source and retrieval date:

Next useful comparison: repeat representative tasks from identical starting SHAs with explicit
behavioral checks. Keep cancelled and failed tasks in the evaluation denominator. Do not derive
a platform success rate from this selected list of merged tasks.
