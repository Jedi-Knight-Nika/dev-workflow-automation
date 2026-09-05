export type Resource<T> = {
  readonly data: T;
  readonly loading: boolean;
  readonly error: string;
  /** Fetches once; subsequent calls are no-ops until refresh() is called. */
  load: () => Promise<void>;
  /** Always re-fetches, even if already loaded. */
  refresh: () => Promise<void>;
};

/**
 * A module-level singleton cache for a GET-style resource, shared across every
 * page that imports it. Call load() on mount (cheap after the first page), and
 * refresh() after a mutation or a live-update signal so every consumer sees
 * the same fresh data without each page re-fetching independently.
 */
export function createResource<T>(fetcher: () => Promise<T>, initial: T): Resource<T> {
  let data = $state(initial);
  let loading = $state(false);
  let error = $state('');
  let loaded = false;
  let inFlight: Promise<void> | null = null;

  async function run() {
    loading = true;
    error = '';
    try {
      data = await fetcher();
      loaded = true;
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      loading = false;
      inFlight = null;
    }
  }

  function load() {
    if (loaded) return Promise.resolve();
    if (!inFlight) inFlight = run();
    return inFlight;
  }

  function refresh() {
    if (!inFlight) inFlight = run();
    return inFlight;
  }

  return {
    get data() {
      return data;
    },
    get loading() {
      return loading;
    },
    get error() {
      return error;
    },
    load,
    refresh
  };
}
