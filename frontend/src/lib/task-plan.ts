import type { Job } from '$lib/types';

export type ThinkerPlan = {
  goal: string;
  targets: string[];
  ordered_steps: string[];
  constraints: string[];
  required_tests: string[];
  risks: string[];
  acceptance_criteria: string[];
};

export function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

export function planFromJobs(currentJobs: Job[]): ThinkerPlan | null {
  const data = [...currentJobs]
    .reverse()
    .find((job) => job.role === 'THINKER' && job.state === 'SUCCEEDED' && job.result)?.result?.data;
  if (
    !data ||
    typeof data.goal !== 'string' ||
    !isStringArray(data.targets) ||
    !isStringArray(data.ordered_steps) ||
    !isStringArray(data.constraints) ||
    !isStringArray(data.required_tests) ||
    !isStringArray(data.risks) ||
    !isStringArray(data.acceptance_criteria)
  )
    return null;
  return data as ThinkerPlan;
}

export function latestThinkerJob(jobs: Job[]): Job | null {
  return (
    [...jobs].reverse().find((job) => job.role === 'THINKER' && job.state === 'SUCCEEDED') ?? null
  );
}
