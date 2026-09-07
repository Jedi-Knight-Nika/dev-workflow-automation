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
  return {
    request,
    stop() {
      stopped = true;
      clearTimeout(timer);
    }
  };
}
