import type { ActivityEvent } from './types';
import type { ReceiptTotals } from './receipts';

export type UsageGroup = ReceiptTotals & {
  id: string;
  label: string;
  calls: number;
  completedCalls: number;
  providerRequests: number;
  unknownRequestRuns: number;
  partialRequestRuns: number;
};
export type RequestCount = { count: number | null; complete: boolean };

export function requestCount(event: ActivityEvent): RequestCount {
  const count = event.payload.request_count;
  return typeof count === 'number' &&
    Number.isSafeInteger(count) &&
    count >= 0 &&
    count <= 1_000_000
    ? { count, complete: event.payload.request_count_complete === true }
    : { count: null, complete: false };
}
export type ModelChange = { task: string; role: string; before: string; after: string; at: string };
export type Economics = {
  tasks: UsageGroup[];
  teams: UsageGroup[];
  roles: UsageGroup[];
  models: UsageGroup[];
  changes: ModelChange[];
};
export type RunIdentity = {
  task: string;
  taskLabel: string;
  team: string;
  teamLabel: string;
  role: string;
  model: string;
};

export function runIdentity(event: ActivityEvent): RunIdentity {
  return {
    task: event.task_id,
    taskLabel: event.task_key || event.task_title,
    team: event.team_id ?? 'unassigned',
    teamLabel: event.team_name ?? 'Unassigned',
    role: String(event.payload.role ?? 'Unknown'),
    model: String(event.payload.model ?? 'Unknown')
  };
}

/** Group the same receipts used by the total; corrections never create another call. */
export function usageGroups(
  calls: Map<string, RunIdentity>,
  receipts: Map<string, { identity: RunIdentity; totals: ReceiptTotals }>,
  changes: ModelChange[],
  requests: Map<string, RequestCount>
): Economics {
  const groups = {
    tasks: new Map<string, UsageGroup>(),
    teams: new Map<string, UsageGroup>(),
    roles: new Map<string, UsageGroup>(),
    models: new Map<string, UsageGroup>()
  };
  const visit = (identity: RunIdentity, add: (group: UsageGroup) => void) => {
    const dimensions = [
      ['tasks', identity.task, identity.taskLabel],
      ['teams', identity.team, identity.teamLabel],
      ['roles', identity.role, identity.role],
      ['models', identity.model, identity.model]
    ] as const;
    for (const [dimension, id, label] of dimensions) {
      let group = groups[dimension].get(id);
      if (!group) {
        group = {
          id,
          label,
          calls: 0,
          completedCalls: 0,
          providerRequests: 0,
          unknownRequestRuns: 0,
          partialRequestRuns: 0,
          cost: 0,
          unknownCosts: 0,
          incompleteUsage: 0,
          inputTokens: 0,
          outputTokens: 0
        };
        groups[dimension].set(id, group);
      }
      add(group);
    }
  };
  for (const [id, identity] of calls)
    visit(identity, (group) => {
      group.calls++;
      const request = requests.get(id);
      group.providerRequests += request?.count ?? 0;
      if (request?.count == null) group.unknownRequestRuns++;
      else if (!request.complete) group.partialRequestRuns++;
    });
  for (const [id, receipt] of receipts)
    visit(receipt.identity, (group) => {
      if (calls.has(id)) group.completedCalls++;
      for (const key of [
        'cost',
        'unknownCosts',
        'incompleteUsage',
        'inputTokens',
        'outputTokens'
      ] as const)
        group[key] += receipt.totals[key];
    });
  const sorted = (values: Map<string, UsageGroup>) =>
    [...values.values()].sort((a, b) => b.cost - a.cost || a.label.localeCompare(b.label));
  return {
    tasks: sorted(groups.tasks),
    teams: sorted(groups.teams),
    roles: sorted(groups.roles),
    models: sorted(groups.models),
    changes
  };
}
