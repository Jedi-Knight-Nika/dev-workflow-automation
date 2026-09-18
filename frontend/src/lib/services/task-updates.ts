import { API_BASE_URL } from '$lib/api';

type TaskUpdateOptions = {
  taskId?: () => string | undefined;
  connected?: (value: boolean) => void;
};

type Subscriber = { refresh: () => void; options: TaskUpdateOptions };
const subscribers = new Set<Subscriber>();
let stream: EventSource | undefined;
let timer: ReturnType<typeof setInterval> | undefined;
let connected = false;

function notify(action: (subscriber: Subscriber) => void) {
  for (const subscriber of subscribers) {
    try {
      action(subscriber);
    } catch (error) {
      console.error('Task update subscriber failed', error);
    }
  }
}

function connect() {
  const current = new EventSource(API_BASE_URL + '/events/stream');
  stream = current;
  current.onopen = () => {
    if (stream !== current) return;
    connected = true;
    notify(({ refresh, options }) => {
      options.connected?.(true);
      refresh();
    });
  };
  current.onerror = () => {
    if (stream !== current) return;
    connected = false;
    notify(({ options }) => options.connected?.(false));
  };
  current.addEventListener('update', (event) => {
    if (stream !== current) return;
    let taskId: string | undefined;
    try {
      const payload = JSON.parse(event.data);
      if (typeof payload?.task_id === 'string') taskId = payload.task_id;
    } catch {
      taskId = undefined;
    }
    notify(({ refresh, options }) => {
      if (!options.taskId || (taskId !== undefined && taskId === options.taskId())) refresh();
    });
  });
  timer = setInterval(() => {
    if (!document.hidden) notify(({ refresh }) => refresh());
  }, 10000);
}

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
  const subscriber = { refresh, options };
  subscribers.add(subscriber);
  if (!stream) {
    try {
      connect();
    } catch (error) {
      subscribers.delete(subscriber);
      throw error;
    }
  } else if (connected) options.connected?.(true);
  return () => {
    if (!subscribers.delete(subscriber) || subscribers.size) return;
    const previous = stream;
    stream = undefined;
    connected = false;
    clearInterval(timer);
    timer = undefined;
    previous?.close();
  };
}
