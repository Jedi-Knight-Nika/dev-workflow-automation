import { API_BASE_URL } from '$lib/api';

type TaskUpdateOptions = {
  taskId?: () => string | undefined;
  connected?: (value: boolean) => void;
};

/** Mount an initial refresh and its event/poll subscription with one cleanup. */
export function startTaskRefresh(
  refresh: { request: () => void; stop: () => void },
  options: TaskUpdateOptions = {}
) {
  refresh.request();
  const unsubscribe = subscribeTaskUpdates(refresh.request, options);
  return () => {
    unsubscribe();
    refresh.stop();
  };
}

/** Shared task events plus reconciliation polling; call only after mounting. */
export function subscribeTaskUpdates(refresh: () => void, options: TaskUpdateOptions = {}) {
  const stream = new EventSource(API_BASE_URL + '/events/stream');
  stream.onopen = () => options.connected?.(true);
  stream.onerror = () => options.connected?.(false);
  stream.addEventListener('update', (event) => {
    if (!options.taskId) {
      refresh();
      return;
    }
    try {
      if (JSON.parse(event.data).task_id === options.taskId()) refresh();
    } catch {
      // Malformed events are reconciled by the bounded poll.
    }
  });
  const timer = setInterval(() => {
    if (!document.hidden) refresh();
  }, 10000);
  return () => {
    stream.close();
    clearInterval(timer);
  };
}
