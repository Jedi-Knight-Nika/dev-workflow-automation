import { activityApi } from './api';
import type { ActivityEvent, Preflight } from './types';

type ActivityStreamOptions = {
  preflight: Preflight;
  detail: number;
  after: number;
  events: ActivityEvent[];
  connection: (connected: boolean) => void;
  reconnect: () => void;
  cursor: (sequence: number) => void;
  status: (preflight: Preflight) => void;
  capacity: (evidence: NonNullable<Preflight['capacity']>) => void;
  append: (event: ActivityEvent, events: ActivityEvent[], preflight: Preflight) => void;
  error: (message: string, pause: boolean) => void;
};

export function subscribeActivity(options: ActivityStreamOptions): () => void {
  let preflight = options.preflight;
  let cursor = options.after;
  let events = options.events;
  let stopped = false;
  let opened = false;
  const source = activityApi.stream(preflight, options.detail, cursor);

  function stop() {
    if (stopped) return;
    stopped = true;
    source.close();
    options.connection(false);
  }

  function fail(message: string, pause = false) {
    stop();
    options.error(message, pause);
  }

  source.onopen = () => {
    if (stopped) return;
    if (opened) options.reconnect();
    opened = true;
    options.connection(true);
  };
  source.onerror = () => {
    if (!stopped) options.connection(false);
  };
  source.addEventListener('status', (event) => {
    if (stopped) return;
    try {
      const status = JSON.parse(event.data);
      if (
        status.capacity &&
        Array.isArray(status.capacity.teams) &&
        status.capacity.through_sequence <= cursor
      )
        options.capacity(status.capacity);
      if (typeof status.delayed === 'boolean') {
        preflight = {
          ...preflight,
          delayed: status.delayed,
          file_history: status.file_history ?? preflight.file_history
        };
        options.status(preflight);
      }
    } catch {
      return;
    }
  });
  source.addEventListener('cursor', (event) => {
    if (stopped) return;
    try {
      const next = JSON.parse(event.data).sequence;
      if (Number.isSafeInteger(next)) {
        cursor = Math.max(cursor, next);
        options.cursor(cursor);
      }
    } catch {
      return;
    }
  });
  source.addEventListener('activity', (event) => {
    if (stopped) return;
    try {
      const item: ActivityEvent = JSON.parse(event.data);
      if (
        !Number.isSafeInteger(item.sequence) ||
        item.sequence <= cursor ||
        typeof item.task_id !== 'string' ||
        !Array.isArray(item.files)
      )
        return;
      const next = [...events, item];
      if (
        next.length > (preflight.max_events || 5000) ||
        new Set(next.map((entry) => entry.task_id)).size > (preflight.max_tasks || 200) ||
        next.reduce((sum, entry) => sum + entry.files.length, 0) > (preflight.max_files || 5000)
      ) {
        fail('Live history reached its limit. Choose a shorter range to continue.', true);
        return;
      }
      cursor = item.sequence;
      events = next;
      preflight = { ...preflight, through_sequence: item.sequence, to: new Date().toISOString() };
      options.cursor(cursor);
      options.append(item, events, preflight);
    } catch {
      fail('A live event could not be read. Reload this view to reconcile history.');
    }
  });
  source.addEventListener('reset', () => {
    if (!stopped)
      fail(
        'Earlier activity has arrived. Reload the view to reconstruct its starting state.',
        true
      );
  });
  source.addEventListener('unavailable', () => {
    if (!stopped) fail('This activity scope is no longer available.');
  });
  return stop;
}
