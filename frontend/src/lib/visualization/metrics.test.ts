import { expect, it } from 'vitest';
import { ReceiptLedger } from './receipts';
import { Replay } from './replay';
import { CanvasRenderer } from './canvas';
import type { ActivityEvent, CapacityEvidence, Frame } from './types';

const start = Date.parse('2026-09-15T00:00:00Z');
const at = (seconds: number) => new Date(start + seconds * 1000).toISOString();
const event = (
  sequence: number,
  kind: string,
  payload: Record<string, unknown> = {}
): ActivityEvent => ({
  sequence,
  id: String(sequence),
  kind,
  occurred_at: at(sequence),
  recorded_at: at(sequence),
  task_id: 'task',
  task_title: 'Task',
  task_key: null,
  team_id: 'team',
  team_name: 'Team',
  project: null,
  actor: 'Developer',
  actor_type: 'agent',
  correlation_id: null,
  payload,
  files: []
});

it('restores cross-task prerequisites and deployment outcomes when seeking backward', () => {
  const replay = new Replay({
    tasks: [],
    events: [
      event(1, 'TASK_DEPENDENCIES_CHANGED', { dependency_ids: ['prerequisite'] }),
      event(2, 'DEPLOYMENT_STATUS_CHANGED', {
        repository_id: 'repo',
        deployment_id: 'deployment',
        observation_id: '2',
        environment: 'production',
        production: true,
        status: 'SUCCESS',
        started_at: at(0)
      }),
      event(3, 'TASK_DEPENDENCIES_CHANGED', { dependency_ids: [] })
    ],
    start,
    mode: 'flow',
    live: false,
    maxEvents: 100,
    maxTasks: 10
  });
  replay.seek(3);
  expect(replay.frame().tasks[0].dependency_ids).toEqual([]);
  expect(replay.frame().deployments.succeeded).toBe(1);
  replay.seek(1);
  expect(replay.frame().tasks[0].dependency_ids).toEqual(['prerequisite']);
  expect(replay.frame().deployments.succeeded).toBe(0);
});

it('counts provider requests independently of runs, corrections and incomplete billing', () => {
  const ledger = new ReceiptLedger();
  const observe = (
    sequence: number,
    kind: string,
    run: string,
    facts: Record<string, unknown> = {}
  ) =>
    ledger.observe(
      event(sequence, kind, { run_id: run, role: 'DEVELOPER', model: 'model', ...facts })
    );
  observe(1, 'AI_RUN_STARTED', 'a');
  expect(ledger.breakdown().roles[0].unknownRequestRuns).toBe(1);
  observe(2, 'AI_RUN_COMPLETED', 'a', {
    request_count: 3,
    request_count_complete: true,
    cost_usd: '1'
  });
  observe(3, 'AI_RUN_COMPLETED', 'b', {
    request_count: 2,
    request_count_complete: false,
    cost_usd: '.5'
  });
  observe(4, 'AI_RUN_COMPLETED', 'c');
  observe(5, 'AI_RUN_COMPLETED', 'd', {
    request_count: 0,
    request_count_complete: true,
    cost_usd: '0'
  });
  observe(6, 'ENGINEERING_COST_RECONCILED', 'a', { cost_usd: '2' });
  observe(1, 'AI_RUN_STARTED', 'a');
  expect(ledger.breakdown().roles[0]).toMatchObject({
    calls: 4,
    completedCalls: 4,
    providerRequests: 5,
    unknownRequestRuns: 1,
    partialRequestRuns: 1,
    cost: 2.5
  });
});

it('separates CI outcomes, reviews and manual takeovers, including when seeking backward', () => {
  const ci = {
    check_key: 'check',
    check_type: 'check_run',
    status: 'FAILURE',
    review_cycle_id: 'notification'
  };
  const entries = [
    event(1, 'CI_NOTIFICATION_RECEIVED', { notification_id: 'notification' }),
    event(2, 'CI_CHECK_UPDATED', ci),
    event(3, 'CI_CHECK_UPDATED', ci),
    event(4, 'CI_CHECK_UPDATED', { ...ci, status: 'SUCCESS' }),
    event(5, 'CI_CHECK_UPDATED', { ...ci, check_key: 'suite', check_type: 'check_suite' }),
    event(6, 'CI_CHECK_UPDATED', { ...ci, check_key: 'pending', status: 'PENDING' }),
    event(7, 'CI_CHECK_UPDATED', { ...ci, check_key: 'cancelled', status: 'CANCELLED' }),
    event(8, 'CI_NOTIFICATION_RECEIVED', { notification_id: 'legacy' }),
    event(9, 'REVIEW_RECEIVED'),
    event(10, 'TASK_STATE_CHANGED', {
      action: 'TAKEOVER',
      version: 2,
      from_manual_takeover: false
    }),
    event(11, 'TASK_STATE_CHANGED', { action: 'TAKEOVER', version: 2 }),
    event(12, 'TASK_STATE_CHANGED', { action: 'TAKEOVER', version: 3, from_manual_takeover: true }),
    event(13, 'TASK_STATE_CHANGED', { action: 'RELEASE_TAKEOVER', version: 4 })
  ];
  const replay = new Replay({
    events: entries,
    tasks: [],
    start,
    mode: 'flow',
    live: false,
    maxEvents: 100,
    maxTasks: 20
  });
  replay.seek(entries.length);
  expect(replay.frame().process).toMatchObject({
    ciFailedChecks: 1,
    ciFailedSuites: 1,
    ciUnknown: 1,
    reviews: 1,
    manualTakeovers: 1,
    manualTasks: 1
  });
  replay.seek(1);
  expect(replay.frame().process).toMatchObject({
    ciFailedChecks: 0,
    ciUnknown: 1,
    reviews: 0,
    manualTakeovers: 0
  });
});

it('refreshes live capacity and idle durations without moving a paused or scrubbed playhead', () => {
  const evidence = (seconds: number, sequence = seconds): CapacityEvidence => ({
    as_of: at(seconds),
    through_sequence: sequence,
    truncated: false,
    teams: [
      {
        id: 'team',
        name: 'Team',
        limits: [{ at: at(0), capacity: 1 }],
        jobs: [{ id: 'job', task_id: 'task', start: at(2), end: null, complete: true }]
      }
    ]
  });
  const frames: Frame[] = [];
  const renderer = new CanvasRenderer(null, (message) => {
    if (message.type === 'FRAME') frames.push(message.frame);
    else throw new Error(message.message);
  });
  renderer.send({
    type: 'LOAD',
    config: {
      events: [
        event(1, 'TASK_CREATED'),
        event(2, 'TASK_STATE_CHANGED', { to_status: 'ACTIVE', to_stage: 'DEVELOPING', version: 2 })
      ],
      tasks: [],
      start,
      mode: 'flow',
      live: true,
      maxEvents: 100,
      maxTasks: 20,
      capacity: evidence(10)
    }
  });
  renderer.send({ type: 'PLAY' });
  renderer.send({ type: 'CAPACITY', evidence: evidence(30) });
  expect(frames.at(-1)?.at).toBe(start + 30_000);
  expect(frames.at(-1)?.bottlenecks.capacity[0].saturatedMs).toBe(28_000);
  const count = frames.length;
  renderer.send({ type: 'CAPACITY', evidence: evidence(20) });
  expect(frames).toHaveLength(count);
  renderer.send({ type: 'PAUSE' });
  renderer.send({ type: 'CAPACITY', evidence: evidence(40) });
  expect(frames.at(-1)?.at).toBe(start + 30_000);
  renderer.send({ type: 'SEEK', index: 1 });
  renderer.send({ type: 'CAPACITY', evidence: evidence(50) });
  expect(frames.at(-1)?.at).toBe(start + 1_000);
  renderer.send({ type: 'PLAY' });
  expect(frames.at(-1)?.at).toBe(start + 50_000);
  renderer.send({ type: 'DISPOSE' });
});
