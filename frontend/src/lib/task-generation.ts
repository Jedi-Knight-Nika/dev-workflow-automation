import type { Job, TaskEvent } from './types';

const ACTIVE_JOB_STATES = new Set(['CLAIMED', 'RUNNING']);

export type TaskGenerationProgress = {
  jobId: string;
  role: string;
  action: string;
  charactersReceived: number;
};

export function taskGenerationProgress(
  events: TaskEvent[],
  jobs: Job[]
): TaskGenerationProgress | null {
  const activeJobs = new Map(
    jobs.filter((job) => ACTIVE_JOB_STATES.has(job.state)).map((job) => [job.id, job])
  );

  for (const event of [...events].sort((left, right) => right.id - left.id)) {
    if (event.event_type !== 'MODEL_STREAM_PROGRESS') continue;

    const jobId = event.payload.job_id;
    const charactersReceived = event.payload.characters_received;
    if (typeof jobId !== 'string' || typeof charactersReceived !== 'number') continue;

    const job = activeJobs.get(jobId);
    if (!job) continue;

    return {
      jobId,
      role: job.role,
      action: job.action,
      charactersReceived
    };
  }

  return null;
}
