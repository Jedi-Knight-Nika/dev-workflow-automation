import { getLiveMetrics, getMonitoringSettings } from './observability';
import type { LiveMetrics } from '$lib/types/observability';

export const operations = $state<{ live: LiveMetrics | null; error: string }>({
  live: null,
  error: ''
});
let subscribers = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let controller: AbortController | undefined;
let refreshSeconds = 5,
  lastSettings = 0;
export function subscribeOperations() {
  subscribers++;
  if (subscribers === 1) {
    controller = new AbortController();
    const signal = controller.signal;
    const refresh = async () => {
      if (!document.hidden) {
        if (Date.now() - lastSettings > 30000) {
          lastSettings = Date.now();
          void getMonitoringSettings()
            .then((s) => (refreshSeconds = s.refresh_seconds))
            .catch(() => {});
        }
        try {
          const value = await getLiveMetrics(signal);
          if (!signal.aborted) {
            operations.live = value;
            operations.error = '';
          }
        } catch {
          if (!signal.aborted) {
            operations.live = null;
            operations.error = 'Live monitoring unavailable';
          }
        }
      }
      if (!signal.aborted) timer = setTimeout(refresh, refreshSeconds * 1000);
    };
    void refresh();
  }
  return () => {
    if (--subscribers === 0) {
      controller?.abort();
      clearTimeout(timer);
    }
  };
}
