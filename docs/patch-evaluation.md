# Bounded patch evaluation

Recorded outcomes and the appendable reporting template live in [Engineering task results](task-results.md).

Keep FAST_PATCH as the baseline. Evaluate repository behavior, not a prescribed tool sequence.
No evaluation should publish, merge, or spend money implicitly: run each selected case through
an explicitly enabled test team with an isolated checkout and a fixed task budget.

## Initial cases

Use real historical tickets, with their original text and the exact commit before the fix:

| Case | Required outcome evidence |
| --- | --- |
| Live Execution drag/resize | Drag, resize, viewport bounds, keyboard control, read-only behavior |
| Desktop startup loader | Desktop build/startup evidence and expected loading screen |
| PR formatting feedback | Same PR updated, scoped formatting passes, no unrelated changes |
| Small backend bug | A failing assertion passes and existing relevant tests still pass |
| Cross-layer change | API contract and consumer agree; combined validation passes |

These are case definitions, not completed trials. Populate starting SHAs and executable
acceptance checks before comparing runs. Do not compare a retry against an already-fixed base.

## Trial record

Record one row per task trial, retaining provider receipts and validation artifacts:

```json
{
  "case_id": "live-execution-drag-resize",
  "starting_sha": "REQUIRED",
  "original_requirement": "REQUIRED: verbatim ticket",
  "task_id": "REQUIRED",
  "harness": "patch",
  "model": "REQUIRED: actual receipt model",
  "effort": "REQUIRED: actual request effort",
  "execution_mode": "FAST_PATCH",
  "model_calls": null,
  "input_tokens": null,
  "cached_input_tokens": null,
  "output_tokens": null,
  "cost_usd": null,
  "wall_seconds": null,
  "full_validation_passed": null,
  "behavior_accepted": null,
  "human_patch_required": null,
  "failure_category": null,
  "evidence_refs": []
}
```

Unknown values stay null, never zero. Include failed-attempt spending when calculating cost
per accepted case. Cached input is a subset of input; do not add it to input again.
Report acceptance rate and total spend divided by accepted outcomes together; if none are
accepted, cost per accepted outcome is unavailable. Formatting success is not UI acceptance.

## Zero-cost regression fixtures

Run from `backend`:

```sh
.venv/bin/pytest -q tests/infrastructure/test_patch_preflight.py tests/infrastructure/test_patch_pipeline.py tests/infrastructure/test_adaptive_patch.py
```

These mocked regressions verify admission/repair bounds and failure handling, not model quality.
Do not represent them as real-ticket benchmark results.
