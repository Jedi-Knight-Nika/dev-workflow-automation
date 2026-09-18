import { describe, expect, it, vi } from 'vitest';
import { activityApi } from './api';
import { subscribeActivity } from './live-stream';
import type { ActivityEvent, Preflight } from './types';

vi.mock('./api', () => ({ activityApi: { stream: vi.fn() } }));

function setup(overrides: Partial<Preflight> = {}) {
  const handlers = new Map<string, (event: { data: string }) => void>();
  const source = {
    onopen: () => {},
    onerror: () => {},
    close: vi.fn(),
    addEventListener: (type: string, handler: (event: { data: string }) => void) => {
      handlers.set(type, handler);
    }
  };
  vi.mocked(activityApi.stream).mockReturnValue(source as unknown as EventSource);
  const options = {
    preflight: { max_events: 2, max_tasks: 2, max_files: 2, ...overrides } as Preflight,
    detail: 2,
    after: 10,
    events: [] as ActivityEvent[],
    connection: vi.fn(),
    reconnect: vi.fn(),
    cursor: vi.fn(),
    status: vi.fn(),
    capacity: vi.fn(),
    append: vi.fn(),
    error: vi.fn()
  };
  const stop = subscribeActivity(options);
  const emit = (type: string, value: unknown) =>
    handlers.get(type)?.({ data: JSON.stringify(value) });
  const event = (sequence: number) => ({ sequence, task_id: 'task', files: [] });
  return { source, options, stop, emit, event, handlers };
}

describe('activity stream lifecycle', () => {
  it('advances monotonically and ignores late events after cleanup', () => {
    const { source, options, stop, emit, event } = setup();
    source.onopen();
    source.onopen();
    expect(options.reconnect).toHaveBeenCalledOnce();
    emit('activity', event(11));
    emit('activity', event(11));
    emit('cursor', { sequence: 15 });
    emit('activity', event(14));
    expect(options.append).toHaveBeenCalledOnce();
    expect(options.cursor).toHaveBeenLastCalledWith(15);
    stop();
    stop();
    emit('activity', event(16));
    source.onopen();
    expect(options.append).toHaveBeenCalledOnce();
    expect(source.close).toHaveBeenCalledOnce();
    expect(options.connection).toHaveBeenLastCalledWith(false);
  });

  it('stops and pauses at the history bound without appending the excess event', () => {
    const { emit, event, options, source } = setup({ max_events: 1 });
    emit('activity', event(11));
    emit('activity', event(12));
    expect(options.append).toHaveBeenCalledOnce();
    expect(options.error).toHaveBeenCalledWith(expect.stringContaining('reached its limit'), true);
    expect(source.close).toHaveBeenCalledOnce();
  });

  it('only applies capacity evidence through the observed cursor', () => {
    const { emit, options } = setup();
    emit('status', { delayed: true, capacity: { teams: [], through_sequence: 11 } });
    expect(options.capacity).not.toHaveBeenCalled();
    expect(options.status).toHaveBeenCalledWith(expect.objectContaining({ delayed: true }));
    emit('status', { capacity: { teams: [], through_sequence: 10 } });
    expect(options.capacity).toHaveBeenCalledOnce();
  });

  it('reports malformed activity and requires explicit reconciliation', () => {
    const { handlers, source, options } = setup();
    handlers.get('activity')?.({ data: '{invalid' });
    expect(source.close).toHaveBeenCalledOnce();
    expect(options.error).toHaveBeenCalledWith(expect.stringContaining('could not be read'), false);
  });
});
