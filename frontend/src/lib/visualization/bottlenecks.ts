import type { CapacityEvidence, TaskState } from './types';
import type { ProcessMetrics } from './process-metrics';

/** A reconnect or delayed response must never replace newer capacity evidence. */
export function newerCapacity(
  previous: CapacityEvidence | undefined,
  next: CapacityEvidence
): boolean {
  const at = Date.parse(next.as_of ?? '');
  return (
    Number.isFinite(at) &&
    Number.isSafeInteger(next.through_sequence) &&
    (next.through_sequence ?? -1) >= (previous?.through_sequence ?? 0) &&
    at >= (Date.parse(previous?.as_of ?? '') || 0)
  );
}

export type CapacitySummary = {
  id: string;
  name: string;
  observedMs: number;
  unknownMs: number;
  saturatedMs: number;
  utilizedSlotMs: number;
  availableSlotMs: number;
  peak: number;
  partial: boolean;
};
export type Bottlenecks = {
  reviewPercent: number | null;
  humanPercent: number | null;
  unknownPercent: number | null;
  waitingHuman: number;
  waitingReview: number;
  blocked: number;
  capacity: CapacitySummary[];
};

/** Sweep immutable interval evidence, counting a task once even if recorded runs overlap. */
function capacitySummary(
  team: CapacityEvidence['teams'][number],
  start: number,
  end: number,
  truncated: boolean
): CapacitySummary {
  const result: CapacitySummary = {
    id: team.id,
    name: team.name,
    observedMs: 0,
    unknownMs: 0,
    saturatedMs: 0,
    utilizedSlotMs: 0,
    availableSlotMs: 0,
    peak: 0,
    partial: truncated || team.jobs.some((job) => !job.complete)
  };
  type Change = { at: number; capacity?: number; task?: string; delta?: number };
  const changes: Change[] = team.limits.map((value) => ({
    at: Date.parse(value.at),
    capacity: value.capacity
  }));
  for (const job of team.jobs) {
    changes.push({ at: Date.parse(job.start), task: job.task_id, delta: 1 });
    if (job.end) changes.push({ at: Date.parse(job.end), task: job.task_id, delta: -1 });
  }
  changes.sort((a, b) => a.at - b.at);
  let at = start,
    capacity: number | null = null;
  const active = new Map<string, number>();
  const accumulate = (until: number) => {
    const elapsed = Math.max(0, Math.min(end, until) - at);
    if (capacity === null) result.unknownMs += elapsed;
    else {
      result.observedMs += elapsed;
      result.availableSlotMs += capacity * elapsed;
      result.utilizedSlotMs += active.size * elapsed;
      if (active.size >= capacity) result.saturatedMs += elapsed;
    }
    if (elapsed) result.peak = Math.max(result.peak, active.size);
    at = Math.max(at, Math.min(end, until));
  };
  for (const change of changes) {
    if (change.at > end) break;
    if (change.at >= start) accumulate(change.at);
    if (change.capacity !== undefined) capacity = change.capacity;
    if (change.task) {
      const count = Math.max(0, (active.get(change.task) ?? 0) + (change.delta ?? 0));
      if (count) active.set(change.task, count);
      else active.delete(change.task);
    }
  }
  accumulate(end);
  return result;
}

export function bottlenecks(
  metrics: ProcessMetrics,
  tasks: TaskState[],
  evidence: CapacityEvidence | undefined,
  start: number,
  end: number
): Bottlenecks {
  const total = Object.values(metrics.time).reduce((sum, duration) => sum + duration, 0);
  const percentage = (duration: number) => (total ? (100 * duration) / total : null);
  return {
    reviewPercent: percentage(metrics.time.review),
    humanPercent: percentage(metrics.time.human),
    unknownPercent: percentage(metrics.time.unknown),
    waitingHuman: tasks.filter((task) => task.status === 'WAITING_HUMAN').length,
    waitingReview: tasks.filter(
      (task) => task.status === 'WAITING_EXTERNAL' && task.wait_reason === 'GITHUB_REVIEW'
    ).length,
    blocked: tasks.filter(
      (task) =>
        task.status === 'WAITING_EXTERNAL' &&
        !['GITHUB_REVIEW', 'GITHUB_CHECKS'].includes(task.wait_reason)
    ).length,
    capacity: (evidence?.teams ?? []).map((team) =>
      capacitySummary(
        team,
        start,
        Math.min(end, evidence?.as_of ? Date.parse(evidence.as_of) : end),
        evidence?.truncated ?? false
      )
    )
  };
}
