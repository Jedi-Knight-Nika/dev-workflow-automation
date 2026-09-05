import { describe, expect, it } from 'vitest';
import { isStringArray, latestThinkerJob, planFromJobs, type ThinkerPlan } from './task-plan';
import type { Job } from './types';

function makeJob(overrides: Partial<Job>): Job {
  return {
    id: 'job-1',
    task_id: 'task-1',
    role: 'THINKER',
    action: 'CREATE_PLAN',
    state: 'SUCCEEDED',
    attempt: 1,
    priority: 3,
    payload: {},
    result: null,
    worker_id: null,
    created_at: '2026-09-05T10:00:00Z',
    started_at: null,
    finished_at: null,
    failure_reason: null,
    retry_not_before: null,
    ...overrides
  };
}

const validPlan: ThinkerPlan = {
  goal: 'Ship the feature',
  targets: ['src/foo.ts'],
  ordered_steps: ['do the thing'],
  constraints: [],
  required_tests: [],
  risks: [],
  acceptance_criteria: ['it works']
};

describe('isStringArray', () => {
  it('accepts an array of strings, including empty', () => {
    expect(isStringArray([])).toBe(true);
    expect(isStringArray(['a', 'b'])).toBe(true);
  });

  it('rejects non-arrays and mixed-type arrays', () => {
    expect(isStringArray('not an array')).toBe(false);
    expect(isStringArray(['a', 1])).toBe(false);
    expect(isStringArray(null)).toBe(false);
  });
});

describe('planFromJobs', () => {
  it('returns null when no successful THINKER job exists', () => {
    expect(planFromJobs([])).toBeNull();
    expect(planFromJobs([makeJob({ state: 'FAILED', result: null })])).toBeNull();
  });

  it('returns null when the result payload is missing required fields', () => {
    const job = makeJob({
      result: {
        protocol_version: 1,
        job_id: 'job-1',
        task_id: 'task-1',
        role: 'THINKER',
        result: 'SUCCEEDED',
        summary: 'done',
        data: { goal: 'missing steps' }
      }
    });
    expect(planFromJobs([job])).toBeNull();
  });

  it('extracts the plan from the latest successful THINKER job', () => {
    const older = makeJob({
      id: 'job-0',
      result: {
        protocol_version: 1,
        job_id: 'job-0',
        task_id: 'task-1',
        role: 'THINKER',
        result: 'SUCCEEDED',
        summary: 'stale',
        data: { ...validPlan, goal: 'stale goal' }
      }
    });
    const newer = makeJob({
      id: 'job-1',
      result: {
        protocol_version: 1,
        job_id: 'job-1',
        task_id: 'task-1',
        role: 'THINKER',
        result: 'SUCCEEDED',
        summary: 'fresh',
        data: { ...validPlan }
      }
    });
    expect(planFromJobs([older, newer])?.goal).toBe('Ship the feature');
  });

  it('ignores a THINKER job that did not succeed', () => {
    const job = makeJob({
      state: 'FAILED',
      result: {
        protocol_version: 1,
        job_id: 'job-1',
        task_id: 'task-1',
        role: 'THINKER',
        result: 'FAILED',
        summary: 'nope',
        data: { ...validPlan }
      }
    });
    expect(planFromJobs([job])).toBeNull();
  });
});

describe('latestThinkerJob', () => {
  it('returns null when there is no successful THINKER job', () => {
    expect(latestThinkerJob([])).toBeNull();
    expect(latestThinkerJob([makeJob({ role: 'EXECUTOR' })])).toBeNull();
  });

  it('returns the most recent successful THINKER job', () => {
    const first = makeJob({ id: 'a' });
    const second = makeJob({ id: 'b' });
    expect(latestThinkerJob([first, second])?.id).toBe('b');
  });
});
