import { activityApi } from './api';
import type { RendererMessage } from './types';

/** Best-effort, bounded measurements; no task IDs, payloads or user text leave the viewer. */
export class ViewerMonitor {
  private started = performance.now();
  private reportedAt = this.started;
  private firstFrame = true;
  private report: Record<string, number | null> = {};
  private timer = setInterval(() => this.flush(), 30_000);

  receive(message: RendererMessage) {
    if (message.type === 'FRAME') {
      if (this.firstFrame) {
        this.report.init_ms = Math.min(3_600_000, performance.now() - this.started);
        this.firstFrame = false;
      }
      if (message.renderMs !== undefined) {
        this.increment('draws');
        this.report.render_ms = Math.min(
          3_600_000,
          (this.report.render_ms ?? 0) + message.renderMs
        );
      }
    } else if (message.code === 'worker_crash') this.increment('worker_crashes', 100);
    else if (message.code === 'graphics_unavailable') this.increment('graphics_failures', 100);
  }

  reconnect() {
    this.increment('reconnects', 10_000);
  }
  gourceFailure() {
    this.increment('gource_failures', 100);
  }
  private increment(key: string, limit = 1_000_000) {
    this.report[key] = Math.min(limit, (this.report[key] ?? 0) + 1);
  }
  flush() {
    const now = performance.now();
    const report = {
      ...this.report,
      session_seconds: Math.min(86_400, (now - this.reportedAt) / 1000)
    };
    this.report = {};
    this.reportedAt = now;
    void activityApi.telemetry(report).catch(() => {
      /* Monitoring never interrupts playback. */
    });
  }
  dispose() {
    clearInterval(this.timer);
    this.flush();
  }
}
