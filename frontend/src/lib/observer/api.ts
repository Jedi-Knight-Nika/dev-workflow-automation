import { api, API_BASE_URL } from '$lib/api';
import type {
  Briefing,
  Conversation,
  FocusMode,
  ObserverMessage,
  ObserverConfiguration,
  ObserverScope,
  ObserverStatus,
  ObserverStreamEvent,
  ObserverInferenceSettings,
  LocalModels,
  ModelDownloadEvent
} from './types';

export function scopeQuery(scope: ObserverScope): string {
  const params = new URLSearchParams();
  if (scope.task_id) params.set('task_id', scope.task_id);
  if (scope.team_id) params.set('team_id', scope.team_id);
  return params.size ? `?${params}` : '';
}

export const observerApi = {
  configuration: () => api<ObserverConfiguration>('/observer/configuration'),
  models: () => api<LocalModels>('/observer/models'),
  configureLocal: (settings: ObserverInferenceSettings) =>
    api<ObserverConfiguration>('/observer/configuration', {
      method: 'PUT',
      body: JSON.stringify(settings)
    }),
  rename: (display_name: string) =>
    api<ObserverConfiguration>('/observer/configuration', {
      method: 'PUT',
      body: JSON.stringify({ display_name })
    }),
  setEnabled: (enabled: boolean) =>
    api<{ enabled: boolean }>('/observer/configuration', {
      method: 'PUT',
      body: JSON.stringify({ enabled })
    }),
  briefing: (scope: ObserverScope, signal?: AbortSignal) =>
    api<Briefing>(`/observer/briefing${scopeQuery(scope)}`, { signal }),
  status: (scope: ObserverScope, signal?: AbortSignal) =>
    api<ObserverStatus>(`/observer/status${scopeQuery(scope)}`, { signal }),
  preferences: (values: { focus?: FocusMode; last_seen_at?: string }) =>
    api<{ focus: FocusMode }>('/observer/preferences', {
      method: 'PUT',
      body: JSON.stringify(values)
    }),
  acknowledge: (id: string) => api(`/observer/events/${id}/acknowledge`, { method: 'POST' }),
  snooze: (id: string, minutes: number) =>
    api(`/observer/events/${id}/snooze`, { method: 'POST', body: JSON.stringify({ minutes }) }),
  conversations: () => api<Conversation[]>('/observer/conversations'),
  history: (id: string) => api<ObserverMessage[]>(`/observer/conversations/${id}`),
  question: (
    message: string,
    context: ObserverScope,
    conversation_id?: string,
    signal?: AbortSignal
  ) =>
    api<{ request_id: string; conversation_id: string }>('/observer/questions', {
      method: 'POST',
      body: JSON.stringify({ message, context, conversation_id }),
      signal
    }),
  usage: () =>
    api<{
      local_runs: number;
      paid_cost_usd: string;
      input_tokens: number | null;
      output_tokens: number | null;
    }>('/observer/usage')
};

export async function streamAnswer(
  id: string,
  receive: (event: ObserverStreamEvent) => void,
  signal: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/observer/questions/${id}/events`, {
    signal,
    headers: { Accept: 'text/event-stream' }
  });
  let completed = false;
  await consumeStream<ObserverStreamEvent>(response, (event) => {
    receive(event);
    if (event.type === 'observer.completed' || event.type === 'observer.failed') completed = true;
  });
  if (!completed && !signal.aborted)
    throw new Error('Assistant disconnected. Your saved conversation is available in history.');
}

export async function installLocalModel(
  model: string,
  receive: (event: ModelDownloadEvent) => void,
  signal: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/observer/models/install`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ model })
  });
  let completed = false;
  await consumeStream<ModelDownloadEvent>(response, (event) => {
    if (event.error) throw new Error(event.error);
    receive(event);
    if (event.done) completed = true;
  });
  if (!completed && !signal.aborted)
    throw new Error('Download interrupted. Retry explicitly when the host is idle.');
}

async function consumeStream<T>(response: Response, receive: (event: T) => void): Promise<void> {
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Assistant request unavailable.');
  }
  if (!response.ok || !response.body) throw new Error('Assistant stream unavailable.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true }).replaceAll('\r\n', '\n');
      if (buffer.length > 65536) throw new Error('Assistant response exceeded its display limit.');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const payload = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n');
        if (!payload) continue;
        receive(JSON.parse(payload) as T);
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

/** Extension point for task cards/charts: send references, never client-supplied measurements. */
export function askObserver(question: string, context?: ObserverScope): void {
  window.dispatchEvent(new CustomEvent('observer:ask', { detail: { question, context } }));
}
