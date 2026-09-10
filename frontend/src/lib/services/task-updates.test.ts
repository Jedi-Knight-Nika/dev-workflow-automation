import { afterEach, expect, it, vi } from 'vitest';
import { subscribeTaskUpdates } from './task-updates';

vi.mock('$lib/api', () => ({ API_BASE_URL: '/api' }));

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup() {
  vi.useFakeTimers();
  const stream = {
    onopen: () => {},
    onerror: () => {},
    addEventListener: vi.fn(),
    close: vi.fn()
  };
  vi.stubGlobal(
    'EventSource',
    class {
      constructor() {
        return stream;
      }
    }
  );
  const document = { hidden: false };
  vi.stubGlobal('document', document);
  return { stream, document };
}

it('filters events using the current task and preserves connection notifications', () => {
  const { stream } = setup();
  const refresh = vi.fn();
  const connected = vi.fn();
  let task = 'first';
  const stop = subscribeTaskUpdates(refresh, { taskId: () => task, connected });
  const update = stream.addEventListener.mock.calls[0][1];
  update({ data: '{broken' });
  update({ data: '{"task_id":"other"}' });
  expect(refresh).not.toHaveBeenCalled();
  update({ data: '{"task_id":"first"}' });
  task = 'second';
  update({ data: '{"task_id":"first"}' });
  update({ data: '{"task_id":"second"}' });
  expect(refresh).toHaveBeenCalledTimes(2);
  stream.onopen();
  stream.onerror();
  expect(connected.mock.calls).toEqual([[true], [false]]);
  stop();
});

it('refreshes the task list, skips hidden polling, and closes resources on cleanup', () => {
  const { stream, document } = setup();
  const refresh = vi.fn();
  const stop = subscribeTaskUpdates(refresh);
  stream.addEventListener.mock.calls[0][1]({ data: 'update' });
  vi.advanceTimersByTime(10000);
  expect(refresh).toHaveBeenCalledTimes(2);
  document.hidden = true;
  vi.advanceTimersByTime(10000);
  expect(refresh).toHaveBeenCalledTimes(2);
  stop();
  document.hidden = false;
  vi.advanceTimersByTime(10000);
  expect(refresh).toHaveBeenCalledTimes(2);
  expect(stream.close).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});
