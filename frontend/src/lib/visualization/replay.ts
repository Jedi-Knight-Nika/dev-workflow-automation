import type {
  ActivityEvent,
  Filters,
  Frame,
  ReplayConfig,
  TaskState,
  WorkPlanSnapshot,
  WorkPlan
} from './types';
import { ProcessAccumulator } from './process-metrics';
import { ReceiptLedger } from './receipts';
import { bottlenecks } from './bottlenecks';
import {
  deploymentEvidence,
  deploymentMetrics,
  type DeploymentEvidence
} from '$lib/delivery/metrics';

export const compareActivity = (a: ActivityEvent, b: ActivityEvent) =>
  Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.sequence - b.sequence;

/** Transport order and replay time are separate: late projections still replay chronologically. */
export class Replay {
  events: ActivityEvent[] = [];
  index = 0;
  private followedAt: number | undefined;
  filters: Filters = { actor: '', kind: '', team: '', communication: true };
  constructor(public config: ReplayConfig) {
    this.append(config.events);
  }

  append(incoming: ActivityEvent[]) {
    const selected = this.events[this.index - 1]?.sequence;
    const unique = new Map(this.events.map((event) => [event.sequence, event]));
    for (const event of incoming) unique.set(event.sequence, event);
    if (unique.size > this.config.maxEvents)
      throw new Error('Live history reached its limit. Choose a shorter range to continue.');
    const tasks = new Set([
      ...this.config.tasks.map((t) => t.id),
      ...[...unique.values()].map((e) => e.task_id)
    ]);
    if (tasks.size > this.config.maxTasks)
      throw new Error('Too many tasks for this view. Choose a Team or task.');
    this.events = [...unique.values()].sort(compareActivity);
    this.index =
      selected === undefined ? 0 : this.events.findIndex((e) => e.sequence === selected) + 1;
  }

  seek(index: number) {
    this.followedAt = undefined;
    this.index = Math.max(0, Math.min(this.events.length, Math.round(index)));
  }

  visible(event: ActivityEvent): boolean {
    const { actor, kind, team, communication } = this.filters;
    return (
      (!actor || event.actor === actor) &&
      (!kind || event.kind === kind) &&
      (!team || event.team_id === team) &&
      (communication || !event.kind.startsWith('MESSAGE_'))
    );
  }

  frame(playing = false): Frame {
    const process = new ProcessAccumulator();
    const tasks = new Map(this.config.tasks.map((t) => [t.id, { ...t }]));
    const updated = new Map(this.config.tasks.map((t) => [t.id, this.config.start]));
    const receipts = new ReceiptLedger();
    const workPlans = new Map<string, WorkPlanSnapshot>();
    const deployments: DeploymentEvidence[] = [];
    let activeMs = 0,
      waitingMs = 0;
    const accumulate = (task: TaskState, at: number) => {
      const elapsed = Math.max(0, at - (updated.get(task.id) ?? at));
      process.interval(task, elapsed);
      if (task.status === 'ACTIVE') activeMs += elapsed;
      else if (['WAITING_HUMAN', 'WAITING_EXTERNAL', 'PAUSED'].includes(task.status))
        waitingMs += elapsed;
      updated.set(task.id, at);
    };
    for (const event of this.events.slice(0, this.index)) {
      let task = tasks.get(event.task_id);
      if (!task) {
        task = {
          id: event.task_id,
          title: event.task_title,
          key: event.task_key,
          team_id: event.team_id,
          team_name: event.team_name,
          project: event.project,
          status: 'UNKNOWN',
          stage: 'UNKNOWN',
          wait_reason: 'NONE',
          version: 0
        };
        tasks.set(task.id, task);
      }
      const at = Date.parse(event.occurred_at);
      if (event.kind === 'TASK_STATE_CHANGED' && Number(event.payload.version) > task.version) {
        accumulate(task, at);
        if (event.payload.to_stage === 'FIXING' && task.stage !== 'FIXING')
          process.values.repairs++;
        task.status = String(event.payload.to_status ?? 'UNKNOWN');
        task.stage = String(event.payload.to_stage ?? 'UNKNOWN');
        task.wait_reason = String(event.payload.wait_reason ?? 'NONE');
        task.version = Number(event.payload.version);
      }
      if (event.kind === 'TASK_CREATED' && task.version === 0 && task.status === 'UNKNOWN') {
        task.status = 'NEW';
        task.stage = 'INTAKE';
        updated.set(task.id, at);
      }
      receipts.observe(event);
      if (event.kind === 'TASK_DEPENDENCIES_CHANGED' && Array.isArray(event.payload.dependency_ids))
        task.dependency_ids = event.payload.dependency_ids.filter(
          (id): id is string => typeof id === 'string'
        );
      if (event.kind === 'WORK_PLAN_UPDATED' && Array.isArray(event.payload.work_plans)) {
        const runId = String(event.payload.run_id);
        workPlans.set(runId, {
          runId,
          task: event.task_key || event.task_title,
          at: event.occurred_at,
          plans: event.payload.work_plans as WorkPlan[]
        });
      }
      process.observe(event, this.config.start);
      if (event.kind === 'DEPLOYMENT_STATUS_CHANGED') {
        const evidence = deploymentEvidence(event.payload, event.occurred_at);
        if (evidence) deployments.push(evidence);
      }
    }
    const last = this.events[this.index - 1];
    const eventAt = last ? Date.parse(last.occurred_at) : this.config.start;
    if (this.config.live && playing && this.index === this.events.length)
      this.followedAt = Math.max(eventAt, Date.parse(this.config.capacity?.as_of ?? '') || eventAt);
    const at = Math.max(eventAt, this.followedAt ?? eventAt);
    for (const task of tasks.values()) accumulate(task, at);
    const metrics = process.result();
    return {
      tasks: [...tasks.values()],
      index: this.index,
      count: this.events.length,
      at,
      playing,
      ...receipts.result(),
      activeMs,
      waitingMs,
      selected: last && this.visible(last) ? last : null,
      process: metrics,
      bottlenecks: bottlenecks(
        metrics,
        [...tasks.values()],
        this.config.capacity,
        this.config.start,
        at
      ),
      economics: receipts.breakdown(),
      workPlans: [...workPlans.values()],
      deployments: deploymentMetrics(deployments)
    };
  }
}

export function replayDelay(
  before: number,
  after: number,
  speed: number,
  realGaps: boolean
): number {
  const gap = Math.max(0, after - before);
  return (realGaps ? gap : Math.min(1500, Math.max(100, gap / 20))) / speed;
}

/** Portable native-Gource export; code rendering itself has no GPL/WASM dependency. */
export function gourceLog(events: ActivityEvent[]): string {
  const clean = (value: string) =>
    [...value].map((char) => (char === '|' || char.charCodeAt(0) < 32 ? '_' : char)).join('');
  const lines: string[] = [];
  for (const event of [...events].sort(compareActivity))
    for (const file of event.files) {
      const prefix = `${Math.floor(Date.parse(event.occurred_at) / 1000)}|${clean(event.actor)}|`;
      const path = `/${clean(file.repository_id)}/${clean(file.path)}`;
      if (file.operation === 'R' && file.previous_path)
        lines.push(`${prefix}D|/${clean(file.repository_id)}/${clean(file.previous_path)}`);
      lines.push(`${prefix}${file.operation === 'R' ? 'A' : file.operation}|${path}`);
    }
  return lines.join('\n');
}
