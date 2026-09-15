import { afterEach, describe, expect, it, vi } from 'vitest';
import { CanvasRenderer } from './canvas';
import { Replay, gourceLog, replayDelay } from './replay';
import type { ActivityEvent, Frame, RendererCommand, ReplayConfig, TaskState } from './types';

const start = Date.parse('2026-09-15T00:00:00Z');
const task: TaskState = {
  id: 'task',
  title: 'Example',
  key: null,
  team_id: 'team',
  team_name: 'Team',
  project: null,
  status: 'WAITING_HUMAN',
  stage: 'REVIEWING',
  wait_reason: 'APPROVAL_REQUIRED',
  version: 1
};
const event = (
  sequence: number,
  seconds: number,
  kind = 'TASK_STATE_CHANGED',
  payload: Record<string, unknown> = {}
): ActivityEvent => ({
  sequence,
  id: String(sequence),
  kind,
  occurred_at: new Date(start + seconds * 1000).toISOString(),
  recorded_at: new Date(start + 100000).toISOString(),
  task_id: 'task',
  task_title: 'Example',
  task_key: null,
  team_id: 'team',
  team_name: 'Team',
  project: null,
  actor_type: 'agent',
  actor: 'Developer',
  correlation_id: null,
  payload,
  files: []
});

describe('activity renderer', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('keeps the same replay results without rebuilding receipts during camera changes', () => {
    const summarize = vi.spyOn(Replay.prototype, 'frame');
    const frames: Frame[] = [];
    const renderer = new CanvasRenderer(null, (message) => {
      if (message.type === 'FRAME') frames.push(message.frame);
      else throw new Error(message.message);
    });
    renderer.send({
      type: 'LOAD',
      config: config([
        event(1, 10, 'TASK_STATE_CHANGED', {
          version: 2,
          to_status: 'ACTIVE',
          to_stage: 'DEVELOPING'
        }),
        event(2, 20, 'AI_RUN_COMPLETED', {
          run_id: 'run',
          cost_usd: '1',
          input_tokens: 100,
          usage_complete: true
        })
      ])
    });
    renderer.send({ type: 'SEEK', index: 2 });
    const before = frames.at(-1);
    const reads = summarize.mock.calls.length;
    const controls: RendererCommand[] = [
      { type: 'PAN', x: 20, y: 10 },
      { type: 'ZOOM', factor: 1.1 },
      { type: 'RESIZE', width: 1200, height: 800, dpr: 2 },
      { type: 'RESET_CAMERA' },
      { type: 'MODE', mode: 'code' },
      { type: 'SPEED', speed: 2, realGaps: false },
      { type: 'PAUSE' }
    ];
    for (const command of controls) {
      renderer.send(command);
      expect(frames.at(-1)).toEqual(before);
    }
    expect(summarize).toHaveBeenCalledTimes(reads);
    renderer.send({
      type: 'FILTER',
      filters: { actor: 'Human', kind: '', team: '', communication: true }
    });
    expect(frames.at(-1)).toEqual({ ...before, selected: null });
    renderer.send({ type: 'SEEK', index: 1 });
    expect(frames.at(-1)?.cost).toBe(0);
    renderer.send({
      type: 'APPEND',
      events: [event(3, 30, 'ENGINEERING_COST_RECONCILED', { run_id: 'run', cost_usd: '2' })]
    });
    expect(frames.at(-1)?.count).toBe(3);
    renderer.send({ type: 'SEEK', index: 3 });
    expect(frames.at(-1)?.cost).toBe(2);
    renderer.send({ type: 'DISPOSE' });
  });

  it('resizes the backing canvas only when its pixel dimensions change', () => {
    let width = 900,
      height = 500,
      allocations = 0;
    const context = {
      canvas: {
        get width() {
          return width;
        },
        set width(value: number) {
          width = value;
          allocations++;
        },
        get height() {
          return height;
        },
        set height(value: number) {
          height = value;
          allocations++;
        }
      },
      setTransform() {},
      fillRect() {},
      beginPath() {},
      moveTo() {},
      lineTo() {},
      stroke() {},
      translate() {},
      save() {},
      restore() {},
      scale() {},
      fillText() {},
      measureText: () => ({ width: 30 })
    } as unknown as CanvasRenderingContext2D;
    const renderer = new CanvasRenderer(context, (message) => {
      if (message.type === 'ERROR') throw new Error(message.message);
    });
    renderer.send({ type: 'LOAD', config: { ...config([]), tasks: [] } });
    renderer.send({ type: 'RESIZE', width: 800, height: 600, dpr: 1 });
    expect(allocations).toBe(2);
    renderer.send({ type: 'PAN', x: 10, y: 10 });
    renderer.send({ type: 'RESIZE', width: 800, height: 600, dpr: 1 });
    expect(allocations).toBe(2);
    renderer.send({ type: 'RESIZE', width: 800, height: 600, dpr: 2 });
    expect(allocations).toBe(4);
    expect([width, height]).toEqual([1600, 1200]);
  });

  it('cancels the old playback timer when replacing a loaded replay', () => {
    vi.useFakeTimers();
    const frames: Frame[] = [];
    const renderer = new CanvasRenderer(null, (message) => {
      if (message.type === 'FRAME') frames.push(message.frame);
    });
    renderer.send({ type: 'LOAD', config: config([event(1, 20)]) });
    renderer.send({ type: 'PLAY' });
    expect(vi.getTimerCount()).toBe(1);
    renderer.send({ type: 'LOAD', config: config([event(2, 40)]) });
    const count = frames.length;
    expect(vi.getTimerCount()).toBe(0);
    vi.runAllTimers();
    expect(frames).toHaveLength(count);
    expect(frames.at(-1)?.playing).toBe(false);
  });
});
const config = (events: ActivityEvent[]): ReplayConfig => ({
  events,
  tasks: [task],
  start,
  mode: 'flow',
  live: false,
  maxEvents: 5000,
  maxTasks: 200
});

describe('activity replay', () => {
  it('replays late commits chronologically, deduplicates reconnection, and preserves a paused position', () => {
    const a = event(1, 20, 'TASK_STATE_CHANGED', {
      version: 3,
      to_status: 'ACTIVE',
      to_stage: 'DEVELOPING'
    });
    const b = event(2, 10, 'TASK_STATE_CHANGED', {
      version: 2,
      to_status: 'PAUSED',
      to_stage: 'REVIEWING'
    });
    const replay = new Replay(config([a]));
    replay.seek(1);
    replay.append([a, b]);
    expect(replay.events.map((e) => e.sequence)).toEqual([2, 1]);
    expect(replay.index).toBe(2);
    expect(replay.frame().tasks[0].status).toBe('ACTIVE');
    replay.seek(1);
    expect(replay.frame().tasks[0].status).toBe('PAUSED');
    replay.seek(0);
    expect(replay.frame().tasks[0]).toEqual(task);
  });
  it('uses original waiting durations even when replay skips the gap', () => {
    const replay = new Replay(
      config([
        event(1, 3600, 'TASK_STATE_CHANGED', {
          version: 2,
          to_status: 'ACTIVE',
          to_stage: 'DEVELOPING'
        }),
        event(2, 7200, 'TASK_STATE_CHANGED', {
          version: 3,
          to_status: 'WAITING_EXTERNAL',
          to_stage: 'REVIEWING'
        })
      ])
    );
    replay.seek(2);
    expect(replay.frame().activeMs).toBe(3600000);
    expect(replay.frame().waitingMs).toBe(3600000);
    expect(replayDelay(start, start + 3600000, 1, false)).toBe(1500);
    expect(replayDelay(start, start + 3600000, 2, true)).toBe(1800000);
  });
  it('never counts reservations or cached input twice, and reconciles unknown cost once', () => {
    const replay = new Replay(
      config([
        event(1, 1, 'AI_RUN_STARTED', { run_id: 'run', cost_usd: '5' }),
        event(2, 2, 'AI_RUN_COMPLETED', {
          run_id: 'run',
          cost_usd: null,
          input_tokens: 100,
          output_tokens: 20,
          cache_read_tokens: 80
        }),
        event(3, 3, 'ENGINEERING_COST_RECONCILED', { run_id: 'run', cost_usd: '0' })
      ])
    );
    replay.seek(1);
    expect(replay.frame().cost).toBe(0);
    expect(replay.frame().unknownCosts).toBe(0);
    replay.seek(2);
    expect(replay.frame().unknownCosts).toBe(1);
    expect(replay.frame().inputTokens).toBe(100);
    replay.seek(3);
    expect(replay.frame().unknownCosts).toBe(0);
    expect(replay.frame().cost).toBe(0);
    expect(replay.frame().inputTokens).toBe(100);
  });
  it('refuses an overflowing buffer without dropping already loaded events', () => {
    const replay = new Replay({ ...config([event(1, 1)]), maxEvents: 1 });
    expect(() => replay.append([event(2, 2)])).toThrow('limit');
    expect(replay.events).toHaveLength(1);
  });
  it('exports renames as delete/add and neutralizes Gource record separators', () => {
    const changed = {
      ...event(1, 0, 'CODE_CHANGED'),
      actor: 'Agent|injected\nline',
      files: [
        {
          repository_id: 'repo',
          operation: 'R' as const,
          path: 'new.ts',
          previous_path: 'old.ts',
          lines_added: 0,
          lines_deleted: 0
        }
      ]
    };
    const lines = gourceLog([changed]).split('\n');
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain('|Agent_injected_line|D|/repo/old.ts');
    expect(lines[1]).toContain('|A|/repo/new.ts');
  });
});

it('separates stage time, waits, repairs and retry queue uncertainty', () => {
  const replay = new Replay(
    config([
      event(1, 10, 'TASK_STATE_CHANGED', {
        version: 2,
        to_status: 'ACTIVE',
        to_stage: 'DEVELOPING'
      }),
      event(2, 15, 'JOB_STARTED', { queued_at: new Date(start + 5000).toISOString(), attempt: 1 }),
      event(3, 20, 'TASK_STATE_CHANGED', {
        version: 3,
        to_status: 'ACTIVE',
        to_stage: 'VALIDATING'
      }),
      event(4, 22, 'VALIDATION_FAILED'),
      event(5, 25, 'TASK_STATE_CHANGED', { version: 4, to_status: 'ACTIVE', to_stage: 'FIXING' }),
      event(6, 26, 'TASK_STATE_CHANGED', { version: 3, to_status: 'ACTIVE', to_stage: 'FIXING' }),
      event(7, 27, 'JOB_STARTED', { queued_at: new Date(start).toISOString(), attempt: 2 }),
      event(8, 30, 'TASK_STATE_CHANGED', {
        version: 5,
        to_status: 'WAITING_EXTERNAL',
        to_stage: 'REVIEWING',
        wait_reason: 'GITHUB_REVIEW'
      }),
      event(9, 40, 'HUMAN_RESPONDED')
    ])
  );
  replay.seek(9);
  const frame = replay.frame();
  expect(frame.process.time).toMatchObject({
    human: 10000,
    coding: 15000,
    validation: 5000,
    review: 10000
  });
  expect(frame.process).toMatchObject({
    queueMs: 10000,
    unknownQueueRuns: 1,
    repairs: 1,
    validationFailed: 1,
    firstValidation: 'failed',
    humanResponses: 1
  });
  expect(frame.activeMs).toBe(20000);
  expect(frame.waitingMs).toBe(20000);
});

it('keeps code summaries explicit when retained file details are incomplete', () => {
  const replay = new Replay(
    config([
      {
        ...event(1, 10, 'CODE_CHANGED', { file_count: 2, lines_added: 7, lines_deleted: 1 }),
        file_status: 'EXPIRED'
      }
    ])
  );
  replay.seek(1);
  expect(replay.frame().process).toMatchObject({
    files: 0,
    added: 7,
    deleted: 1,
    incompleteFiles: true
  });
});

it('restores dependency snapshots when seeking backward without changing execution state', () => {
  const plans = (status: string) => [
    {
      revision: 0,
      units: [
        { id: 'schema', depends_on: [], status: 'READY' },
        { id: 'api', depends_on: [0], status }
      ]
    }
  ];
  const replay = new Replay(
    config([
      event(1, 10, 'WORK_PLAN_UPDATED', { run_id: 'run', work_plans: plans('RUNNING') }),
      event(2, 20, 'WORK_PLAN_UPDATED', { run_id: 'run', work_plans: plans('READY') })
    ])
  );
  replay.seek(2);
  expect(replay.frame().workPlans[0].plans[0].units[1].status).toBe('READY');
  replay.seek(1);
  expect(replay.frame().workPlans[0].plans[0].units[1]).toEqual({
    id: 'api',
    depends_on: [0],
    status: 'RUNNING'
  });
  expect(replay.frame().tasks[0]).toEqual(task);
  replay.seek(0);
  expect(replay.frame().workPlans).toEqual([]);
});
