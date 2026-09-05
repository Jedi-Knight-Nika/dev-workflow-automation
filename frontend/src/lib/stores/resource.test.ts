import { describe, expect, it, vi } from 'vitest';
import { createResource } from './resource.svelte';

describe('createResource', () => {
  it('starts with the initial value and is not loading', () => {
    const resource = createResource(async () => ['fetched'], ['initial']);
    expect(resource.data).toEqual(['initial']);
    expect(resource.loading).toBe(false);
    expect(resource.error).toBe('');
  });

  it('load() fetches once and caches on subsequent calls', async () => {
    const fetcher = vi.fn(async () => ['a', 'b']);
    const resource = createResource(fetcher, [] as string[]);

    await resource.load();
    expect(resource.data).toEqual(['a', 'b']);
    expect(fetcher).toHaveBeenCalledTimes(1);

    await resource.load();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('refresh() always re-fetches even when already loaded', async () => {
    let call = 0;
    const fetcher = vi.fn(async () => {
      call += 1;
      return [`result-${call}`];
    });
    const resource = createResource(fetcher, [] as string[]);

    await resource.load();
    expect(resource.data).toEqual(['result-1']);

    await resource.refresh();
    expect(resource.data).toEqual(['result-2']);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('captures a failed fetch in error and leaves stale data in place', async () => {
    const fetcher = vi.fn(async () => {
      throw new Error('network down');
    });
    const resource = createResource(fetcher, ['stale']);

    await resource.load();
    expect(resource.error).toBe('network down');
    expect(resource.data).toEqual(['stale']);
    expect(resource.loading).toBe(false);
  });

  it('concurrent load() calls dedupe into a single in-flight fetch', async () => {
    const fetcher = vi.fn(async () => ['done']);
    const resource = createResource(fetcher, [] as string[]);

    const first = resource.load();
    const second = resource.load();
    await Promise.all([first, second]);

    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
