import { describe, expect, it } from 'vitest';
import { taskGenerationProgress } from './task-generation';
import type { Job, TaskEvent } from './types';

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    task_id: 'task-1',
    role: 'EXECUTOR',
    action: 'IMPLEMENT_PLAN',
    state: 'RUNNING',
    attempt: 1,
    priority: 3,
    payload: {},
    result: null,
    worker_id: 'worker-1',
    created_at: '2026-09-06T10:00:00Z',
    started_at: '2026-09-06T10:01:00Z',
    finished_at: null,
    failure_reason: null,
    retry_not_before: null,
    ...overrides
  };
}

function makeEvent(overrides: Partial<TaskEvent> = {}): TaskEvent {
  return {
    id: 1,
    task_id: 'task-1',
    source: 'WORKER',
    event_type: 'MODEL_STREAM_PROGRESS',
    payload: { job_id: 'job-1', characters_received: 2048 },
    created_at: '2026-09-06T10:02:00Z',
    ...overrides
  };
}

describe('taskGenerationProgress', () => {
  it('returns progress for the latest active streaming job', () => {
    const progress = taskGenerationProgress(
      [makeEvent(), makeEvent({ id: 2, payload: { job_id: 'job-1', characters_received: 4096 } })],
      [makeJob()]
    );

    expect(progress).toEqual({
      jobId: 'job-1',
      role: 'EXECUTOR',
      action: 'IMPLEMENT_PLAN',
      charactersReceived: 4096
    });
  });

  it('ignores historical progress after the job stops running', () => {
    expect(taskGenerationProgress([makeEvent()], [makeJob({ state: 'SUCCEEDED' })])).toBeNull();
  });

  it('ignores malformed progress payloads and unrelated events', () => {
    expect(
      taskGenerationProgress(
        [
          makeEvent({ event_type: 'JOB_STARTED' }),
          makeEvent({ id: 2, payload: { job_id: 'job-1', characters_received: 'many' } })
        ],
        [makeJob()]
      )
    ).toBeNull();
  });
});
