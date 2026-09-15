import type { ActivityEvent } from './types';
import {
  runIdentity,
  usageGroups,
  requestCount,
  type RequestCount,
  type ModelChange,
  type RunIdentity
} from './economics';

export type ReceiptTotals = {
  cost: number;
  unknownCosts: number;
  incompleteUsage: number;
  inputTokens: number;
  outputTokens: number;
};

const numeric = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
};

/** The same receipt semantics serve replay totals and inspector snapshots. */
export class ReceiptLedger {
  private runs = new Map<
    string,
    { cost: number | null; input: number; output: number; complete: boolean; identity: RunIdentity }
  >();
  private calls = new Map<string, RunIdentity>();
  private requests = new Map<string, RequestCount>();
  private lastModel = new Map<string, string>();
  private changes: ModelChange[] = [];
  observe(event: ActivityEvent) {
    const id = String(event.payload.run_id);
    if (
      event.kind === 'AI_RUN_COMPLETED' ||
      (event.kind === 'AI_RUN_STARTED' && !this.runs.has(id))
    )
      this.requests.set(id, requestCount(event));
    if (
      (event.kind === 'AI_RUN_STARTED' || event.kind === 'AI_RUN_COMPLETED') &&
      !this.calls.has(id)
    ) {
      const identity = runIdentity(event),
        key = `${identity.task}:${identity.role}`;
      this.calls.set(id, identity);
      const previous = this.lastModel.get(key);
      if (identity.model !== 'Unknown') {
        if (previous && previous !== identity.model)
          this.changes.push({
            task: identity.taskLabel,
            role: identity.role,
            before: previous,
            after: identity.model,
            at: event.occurred_at
          });
        this.lastModel.set(key, identity.model);
      }
    }
    if (event.kind === 'AI_RUN_COMPLETED') {
      this.calls.set(id, runIdentity(event));
      this.runs.set(String(event.payload.run_id), {
        cost: numeric(event.payload.cost_usd),
        input: numeric(event.payload.input_tokens) ?? 0,
        output: numeric(event.payload.output_tokens) ?? 0,
        complete: event.payload.usage_complete === true,
        identity: this.calls.get(id) ?? runIdentity(event)
      });
    } else if (event.kind === 'ENGINEERING_COST_RECONCILED') {
      const id = String(event.payload.run_id),
        previous = this.runs.get(id);
      this.runs.set(id, {
        cost: numeric(event.payload.cost_usd),
        input: previous?.input ?? 0,
        output: previous?.output ?? 0,
        complete: previous?.complete ?? false,
        identity: previous?.identity ?? this.calls.get(id) ?? runIdentity(event)
      });
    }
  }
  result() {
    const usage = [...this.runs.values()];
    return {
      cost: usage.reduce((sum, run) => sum + (run.cost ?? 0), 0),
      unknownCosts: usage.filter((run) => run.cost === null).length,
      incompleteUsage: usage.filter((run) => !run.complete).length,
      inputTokens: usage.reduce((sum, run) => sum + run.input, 0),
      outputTokens: usage.reduce((sum, run) => sum + run.output, 0)
    };
  }
  breakdown() {
    return usageGroups(
      this.calls,
      new Map(
        [...this.runs].map(([id, run]) => [
          id,
          {
            identity: run.identity,
            totals: {
              cost: run.cost ?? 0,
              unknownCosts: run.cost === null ? 1 : 0,
              incompleteUsage: run.complete ? 0 : 1,
              inputTokens: run.input,
              outputTokens: run.output
            }
          }
        ])
      ),
      this.changes,
      this.requests
    );
  }
}

export function receiptsBefore(events: ActivityEvent[], selected: ActivityEvent | null) {
  const ledger = new ReceiptLedger();
  if (selected)
    for (const event of events) {
      if (event.sequence === selected.sequence) break;
      if (event.task_id === selected.task_id) ledger.observe(event);
    }
  return ledger.result();
}
