/** Track which response still owns the view; requests themselves keep running. */
export function createLatestRequest() {
  let version = 0;
  return {
    begin() {
      const current = ++version;
      return () => current === version;
    },
    invalidate() {
      version++;
    }
  };
}

/** Coalesce event bursts without overlapping requests or starving continuous streams. */
export function createLiveRefresh(load: () => Promise<void>, delay = 350) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let running = false;
  let pending = false;
  let stopped = false;
  async function drain() {
    timer = undefined;
    if (running || stopped) return;
    running = true;
    pending = false;
    try {
      await load();
    } finally {
      running = false;
      if (pending && !stopped) request();
    }
  }
  function request() {
    if (stopped) return;
    pending = true;
    if (!timer && !running)
      timer = setTimeout(() => {
        void drain();
      }, delay);
  }
  /** Run without waiting for the debounce, still serialized against a load already in flight. */
  function now() {
    if (stopped) return;
    clearTimeout(timer);
    timer = undefined;
    if (running) pending = true;
    else void drain();
  }
  return {
    request,
    now,
    stop() {
      stopped = true;
      clearTimeout(timer);
    }
  };
}
