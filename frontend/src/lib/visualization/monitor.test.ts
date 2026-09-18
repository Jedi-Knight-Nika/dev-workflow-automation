import { afterEach, expect, it, vi } from 'vitest';
import { activityApi } from './api';
import { ViewerMonitor } from './monitor';
import { ReceiptLedger, receiptsBefore } from './receipts';
import type { ActivityEvent } from './types';

vi.mock('./api', () => ({ activityApi: { telemetry: vi.fn().mockResolvedValue(undefined) } }));
afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

it('reports deltas and clears its timer when the viewer closes', () => {
  vi.useFakeTimers();
  const monitor = new ViewerMonitor();
  monitor.reconnect();
  monitor.receive({ type: 'ERROR', code: 'worker_crash', message: 'fallback' });
  monitor.flush();
  expect(activityApi.telemetry).toHaveBeenLastCalledWith(
    expect.objectContaining({ reconnects: 1, worker_crashes: 1 })
  );
  monitor.dispose();
  expect(activityApi.telemetry).toHaveBeenLastCalledWith({ session_seconds: expect.any(Number) });
  vi.advanceTimersByTime(60_000);
  expect(activityApi.telemetry).toHaveBeenCalledTimes(2);
});

it('uses the same correction semantics before a selected event as the replay', () => {
  const events = [
    {
      sequence: 1,
      task_id: 'task',
      kind: 'AI_RUN_COMPLETED',
      payload: { run_id: 'run', cost_usd: '1', input_tokens: 100, usage_complete: true }
    },
    {
      sequence: 2,
      task_id: 'task',
      kind: 'ENGINEERING_COST_RECONCILED',
      payload: { run_id: 'run', cost_usd: '2' }
    },
    {
      sequence: 3,
      task_id: 'other',
      kind: 'AI_RUN_COMPLETED',
      payload: { run_id: 'other', cost_usd: '99' }
    },
    { sequence: 4, task_id: 'task', kind: 'TASK_PAUSED', payload: {} }
  ] as ActivityEvent[];
  const ledger = new ReceiptLedger();
  events.slice(0, 2).forEach((event) => ledger.observe(event));
  expect(receiptsBefore(events, events[3])).toEqual(ledger.result());
  expect(receiptsBefore(events, events[1]).cost).toBe(1);
  expect(receiptsBefore(events, events[3])).toMatchObject({ cost: 2, inputTokens: 100 });
});

it('compares receipts by task, Team and role without counting corrections as calls', () => {
  const ledger = new ReceiptLedger();
  const event = (
    sequence: number,
    kind: string,
    run: string,
    model: string,
    cost?: string
  ): ActivityEvent => ({
    sequence,
    id: String(sequence),
    kind,
    task_id: 'task',
    task_title: 'Task',
    team_id: 'team',
    team_name: 'Team',
    occurred_at: `2026-09-15T00:00:0${sequence}Z`,
    recorded_at: '2026-09-15T00:00:00Z',
    task_key: null,
    project: null,
    actor: 'Developer',
    actor_type: 'agent',
    correlation_id: null,
    files: [],
    payload: {
      run_id: run,
      model,
      role: 'DEVELOPER',
      cost_usd: cost,
      usage_complete: true,
      input_tokens: 10
    }
  });
  ledger.observe(event(1, 'AI_RUN_STARTED', 'a', 'model-a'));
  ledger.observe(event(2, 'AI_RUN_COMPLETED', 'a', 'model-a', '1'));
  ledger.observe(event(3, 'AI_RUN_STARTED', 'b', 'model-b'));
  ledger.observe(event(4, 'AI_RUN_COMPLETED', 'b', 'model-b'));
  ledger.observe(event(5, 'ENGINEERING_COST_RECONCILED', 'b', '', '2'));
  const result = ledger.breakdown();
  for (const groups of [result.tasks, result.teams, result.roles])
    expect(groups[0]).toMatchObject({
      cost: 3,
      calls: 2,
      completedCalls: 2,
      inputTokens: 20,
      unknownCosts: 0
    });
  expect(result.models.map((group) => [group.label, group.cost])).toEqual([
    ['model-b', 2],
    ['model-a', 1]
  ]);
  expect(result.changes).toEqual([
    {
      task: 'Task',
      role: 'DEVELOPER',
      before: 'model-a',
      after: 'model-b',
      at: '2026-09-15T00:00:03Z'
    }
  ]);
});
