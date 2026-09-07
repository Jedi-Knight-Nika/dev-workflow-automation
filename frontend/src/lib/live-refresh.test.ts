import { afterEach, expect, it, vi } from 'vitest';
import { createLiveRefresh } from './live-refresh';
afterEach(() => vi.useRealTimers());
it('coalesces event bursts and never overlaps requests', async () => {
  vi.useFakeTimers();
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const load = vi
    .fn()
    .mockImplementationOnce(() => pending)
    .mockResolvedValue(undefined);
  const refresh = createLiveRefresh(load, 100);
  for (let i = 0; i < 100; i++) refresh.request();
  await vi.advanceTimersByTimeAsync(100);
  expect(load).toHaveBeenCalledTimes(1);
  refresh.request();
  await vi.advanceTimersByTimeAsync(1000);
  expect(load).toHaveBeenCalledTimes(1);
  release();
  await vi.advanceTimersByTimeAsync(100);
  expect(load).toHaveBeenCalledTimes(2);
  refresh.request();
  refresh.stop();
  await vi.advanceTimersByTimeAsync(1000);
  expect(load).toHaveBeenCalledTimes(2);
});
