import { api, API_BASE_URL } from '$lib/api';
import type {
  ActivityAggregate,
  ActivityEvent,
  Inspection,
  Preflight,
  Scope,
  TaskState
} from './types';

export function windowQuery(flight: Preflight, detail: number): URLSearchParams {
  const query = new URLSearchParams({
    scope_type: flight.scope.type,
    from: flight.from,
    to: flight.to,
    detail: String(detail)
  });
  if (flight.scope.id) query.set('scope_id', flight.scope.id);
  return query;
}

export const activityApi = {
  aggregate(flight: Preflight, detail: number, signal: AbortSignal) {
    const query = windowQuery(flight, detail);
    query.set('through_sequence', String(flight.through_sequence));
    return api<ActivityAggregate>(`/visualization/aggregate?${query}`, { signal });
  },
  inspect(flight: Preflight, detail: number, sequence: number, signal: AbortSignal) {
    const query = windowQuery(flight, detail);
    query.set('through_sequence', String(flight.through_sequence));
    return api<Inspection>(`/visualization/inspect/${sequence}?${query}`, { signal });
  },
  telemetry: (report: Record<string, number | null>) =>
    api<void>('/visualization/telemetry', {
      method: 'POST',
      body: JSON.stringify(report),
      keepalive: true
    }),
  scopes: (signal: AbortSignal) =>
    api<{
      teams: { id: string; name: string }[];
      repositories: { id: string; name: string }[];
      projects: { id: string; name: string }[];
      truncated: boolean;
    }>('/visualization/scopes', { signal }),
  preflight: (scope: Scope, from: string, to: string | null, detail: number, signal: AbortSignal) =>
    api<Preflight>('/visualization/preflight', {
      method: 'POST',
      body: JSON.stringify({ scope, from, to, detail }),
      signal
    }),
  async load(flight: Preflight, detail: number, signal: AbortSignal) {
    const query = windowQuery(flight, detail);
    query.set('through_sequence', String(flight.through_sequence));
    const baseline = await api<{ tasks: TaskState[] }>(`/visualization/baseline?${query}`, {
      signal
    });
    const events: ActivityEvent[] = [];
    let files = 0;
    let cursor = 0;
    while (true) {
      query.set('after_sequence', String(cursor));
      const page = await api<{ events: ActivityEvent[]; next_sequence: number; has_more: boolean }>(
        `/visualization/events?${query}`,
        { signal }
      );
      events.push(...page.events);
      files += page.events.reduce((sum, event) => sum + event.files.length, 0);
      if (files > flight.max_files) throw new Error('Choose a smaller range for file activity.');
      if (events.length > flight.max_events)
        throw new Error('Choose a smaller time range or scope.');
      if (!page.has_more) break;
      if (page.next_sequence <= cursor)
        throw new Error('Activity history did not advance. Try again.');
      cursor = page.next_sequence;
    }
    return { events, tasks: baseline.tasks };
  },
  stream(flight: Preflight, detail: number, after: number) {
    const query = windowQuery(flight, detail);
    query.delete('to');
    query.set('after_sequence', String(after));
    return new EventSource(`${API_BASE_URL}/visualization/stream?${query}`);
  }
};
