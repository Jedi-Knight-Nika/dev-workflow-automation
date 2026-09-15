import { newerCapacity } from './bottlenecks';
import { Replay, replayDelay } from './replay';
import { drawRelations, type CanvasContext, type CanvasHit } from './canvas-relations';
import type { ActivityEvent, Frame, RendererCommand, RendererMessage, TaskState } from './types';

const stages = [
  'INTAKE',
  'PLANNING',
  'DEVELOPING',
  'VALIDATING',
  'PUBLISHING',
  'REVIEWING',
  'FIXING',
  'MERGING',
  'COMPLETE'
];
const colors: Record<string, string> = {
  agent: '#67e8f9',
  human: '#f9a8d4',
  system: '#cbd5e1',
  integration: '#c4b5fd'
};
const stateColor = (task: TaskState) =>
  task.status === 'ACTIVE'
    ? '#67e8f9'
    : task.status.startsWith('WAITING') || task.status === 'PAUSED'
      ? '#fbbf24'
      : task.status === 'FAILED'
        ? '#fb7185'
        : task.status === 'MERGED'
          ? '#6ee7b7'
          : '#94a3b8';

/** Canvas and playback run in a Worker; the null context is an accessible timeline fallback. */
export class CanvasRenderer {
  private replay: Replay | null = null;
  private frame: Frame | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private playing = false;
  private speed = 1;
  private realGaps = false;
  private width = 900;
  private height = 500;
  private dpr = 1;
  private zoom = 1;
  private pan = { x: 0, y: 0 };
  private hits: CanvasHit[] = [];

  constructor(
    private context: CanvasContext | null,
    private receive: (message: RendererMessage) => void
  ) {}

  send(command: RendererCommand): void {
    let rebuild = true;
    try {
      switch (command.type) {
        case 'INIT':
          this.context = command.canvas.getContext('2d');
          if (!this.context) this.graphicsUnavailable();
          break;
        case 'LOAD':
          clearTimeout(this.timer);
          this.replay = new Replay(command.config);
          this.playing = false;
          if (command.config.live) this.replay.seek(this.replay.events.length);
          break;
        case 'APPEND':
          this.replay?.append(command.events);
          if (this.playing && this.replay?.config.live) this.replay.seek(this.replay.events.length);
          break;
        case 'CAPACITY':
          if (!this.replay || !newerCapacity(this.replay.config.capacity, command.evidence)) return;
          this.replay.config.capacity = command.evidence;
          break;
        case 'PLAY':
          this.playing = true;
          if (this.replay?.config.live) this.replay.seek(this.replay.events.length);
          else if (this.replay?.index === this.replay?.events.length) this.replay?.seek(0);
          this.schedule();
          break;
        case 'PAUSE':
          this.playing = false;
          clearTimeout(this.timer);
          rebuild = false;
          break;
        case 'SEEK':
          this.replay?.seek(command.index);
          this.schedule();
          break;
        case 'SPEED':
          this.speed = command.speed;
          this.realGaps = command.realGaps;
          this.schedule();
          rebuild = false;
          break;
        case 'MODE':
          if (this.replay) this.replay.config.mode = command.mode;
          this.resetCamera();
          rebuild = false;
          break;
        case 'FILTER':
          if (this.replay) this.replay.filters = command.filters;
          break;
        case 'RESIZE':
          this.width = command.width;
          this.height = command.height;
          this.dpr = Math.min(2, command.dpr);
          rebuild = false;
          break;
        case 'PAN':
          this.pan.x += command.x;
          this.pan.y += command.y;
          rebuild = false;
          break;
        case 'ZOOM':
          this.zoom = Math.min(3, Math.max(0.4, this.zoom * command.factor));
          rebuild = false;
          break;
        case 'RESET_CAMERA':
          this.resetCamera();
          rebuild = false;
          break;
        case 'SELECT': {
          const x = (command.x - this.pan.x) / this.zoom,
            y = (command.y - this.pan.y) / this.zoom;
          const hit = this.hits.find(
            (h) => x >= h.x && x <= h.x + h.width && y >= h.y && y <= h.y + h.height
          );
          if (hit && this.frame)
            this.receive({ type: 'FRAME', frame: { ...this.frame, selected: hit.event } });
          return;
        }
        case 'DISPOSE':
          clearTimeout(this.timer);
          this.playing = false;
          this.replay = null;
          this.frame = null;
          this.hits = [];
          return;
      }
      this.update(rebuild);
    } catch {
      this.playing = false;
      clearTimeout(this.timer);
      this.receive({
        type: 'ERROR',
        code: 'limit',
        message: 'This view reached its rendering limit. Narrow the range or reload the replay.'
      });
    }
  }

  private resetCamera() {
    this.zoom = 1;
    this.pan = { x: 0, y: 0 };
  }
  private schedule() {
    clearTimeout(this.timer);
    const replay = this.replay;
    if (!this.playing || !replay || replay.config.live) return;
    const next = replay.events[replay.index];
    if (!next) {
      this.playing = false;
      return;
    }
    const before = replay.events[replay.index - 1];
    const delay = replayDelay(
      before ? Date.parse(before.occurred_at) : replay.config.start,
      Date.parse(next.occurred_at),
      this.speed,
      this.realGaps
    );
    this.timer = setTimeout(
      () => {
        replay.seek(replay.index + 1);
        this.schedule();
        this.update();
      },
      Math.min(2_147_483_647, delay)
    );
  }

  private update(rebuild = true) {
    if (!this.replay) return;
    const started = performance.now();
    // Camera and playback controls do not change historical task state or receipts.
    this.frame =
      rebuild || !this.frame
        ? this.replay.frame(this.playing)
        : { ...this.frame, playing: this.playing };
    try {
      this.draw(this.frame);
    } catch {
      this.context = null;
      this.hits = [];
      this.graphicsUnavailable();
    }
    this.receive({
      type: 'FRAME',
      frame: this.frame,
      ...(this.context ? { renderMs: performance.now() - started } : {})
    });
  }

  private graphicsUnavailable() {
    this.receive({
      type: 'ERROR',
      code: 'graphics_unavailable',
      message: 'Graphics are unavailable. Use the timeline and event inspector below.'
    });
  }

  private draw(frame: Frame) {
    const ctx = this.context;
    if (!ctx || !this.replay) return;
    const width = Math.round(this.width * this.dpr),
      height = Math.round(this.height * this.dpr);
    if (ctx.canvas.width !== width) ctx.canvas.width = width;
    if (ctx.canvas.height !== height) ctx.canvas.height = height;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = '#080e1b';
    ctx.fillRect(0, 0, this.width, this.height);
    ctx.strokeStyle = '#152033';
    ctx.lineWidth = 1;
    for (let x = 0; x < this.width; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, this.height);
      ctx.stroke();
    }
    for (let y = 0; y < this.height; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();
    }
    ctx.translate(this.pan.x, this.pan.y);
    ctx.scale(this.zoom, this.zoom);
    ctx.font = '12px system-ui';
    this.hits = [];
    const visible = this.replay.events.slice(0, frame.index).filter((e) => this.replay?.visible(e));
    const touched = new Set(visible.map((e) => e.task_id));
    const tasks = frame.tasks.filter(
      (t) =>
        (!this.replay?.filters.team || t.team_id === this.replay.filters.team) &&
        ((!this.replay?.filters.actor && !this.replay?.filters.kind) || touched.has(t.id))
    );
    const latest = new Map(visible.map((e) => [e.task_id, e]));
    if (this.replay.config.mode === 'code') this.code(visible);
    else {
      const links = this.replay.filters.communication
        ? drawRelations(ctx, visible, this.width)
        : [];
      const offset = links.length ? 95 : 0;
      ctx.save();
      ctx.translate(0, offset);
      if (this.replay.config.mode === 'workspace') this.workspace(tasks, latest);
      else this.flow(tasks, latest);
      ctx.restore();
      this.hits = [...links, ...this.hits.map((hit) => ({ ...hit, y: hit.y + offset }))];
    }
    if (!visible.length && !tasks.length)
      this.label('No recorded activity in this part of the replay.', 30, 70, '#94a3b8');
  }

  private label(text: string, x: number, y: number, color = '#cbd5e1', width = 190) {
    const ctx = this.context!;
    ctx.fillStyle = color;
    while (text.length > 1 && ctx.measureText(text).width > width) text = text.slice(0, -2) + '…';
    ctx.fillText(text, x, y);
  }

  private card(task: TaskState, x: number, y: number, width: number, event?: ActivityEvent) {
    const ctx = this.context!;
    ctx.fillStyle = '#111d30';
    ctx.strokeStyle = stateColor(task);
    ctx.lineWidth = event?.sequence === this.frame?.selected?.sequence ? 2 : 1;
    ctx.beginPath();
    ctx.roundRect(x, y, width, 66, 8);
    ctx.fill();
    ctx.stroke();
    this.label(task.key || task.title, x + 10, y + 20, '#f1f5f9', width - 20);
    this.label(task.status.replaceAll('_', ' '), x + 10, y + 38, stateColor(task), width - 20);
    if (event) {
      this.label(event.actor, x + 10, y + 55, colors[event.actor_type] || '#94a3b8', width - 20);
      this.hits.push({ x, y, width, height: 66, event });
    }
  }

  private flow(tasks: TaskState[], latest: Map<string, ActivityEvent>) {
    const columnWidth = Math.max(125, (this.width - 40) / stages.length);
    stages.forEach((stage, index) =>
      this.label(stage, 20 + index * columnWidth, 32, '#94a3b8', columnWidth - 12)
    );
    const rows = new Map<number, number>();
    for (const task of tasks) {
      const column = Math.max(0, stages.indexOf(task.stage));
      const row = rows.get(column) || 0;
      rows.set(column, row + 1);
      this.card(
        task,
        20 + column * columnWidth,
        55 + row * 80,
        columnWidth - 12,
        latest.get(task.id)
      );
    }
  }

  private workspace(tasks: TaskState[], latest: Map<string, ActivityEvent>) {
    const groups = new Map<string, TaskState[]>();
    for (const task of tasks) {
      const key = `${task.project || 'Workspace'} / ${task.team_name || 'Unassigned'}`;
      const group = groups.get(key);
      if (group) group.push(task);
      else groups.set(key, [task]);
    }
    const columns = Math.max(1, Math.floor(this.width / 285));
    const heights = Array.from({ length: columns }, () => 25);
    let index = 0;
    for (const [name, group] of groups) {
      const column = index++ % columns,
        y = heights[column],
        x = 20 + column * 285;
      this.label(name, x, y, '#c4b5fd', 260);
      group.forEach((task, row) => this.card(task, x, y + 18 + row * 78, 260, latest.get(task.id)));
      heights[column] += 58 + group.length * 78;
    }
  }

  private code(events: ActivityEvent[]) {
    const files = new Map<string, { path: string; event: ActivityEvent; removed: boolean }>();
    for (const event of events)
      for (const file of event.files) {
        if (file.previous_path) files.delete(file.repository_id + '/' + file.previous_path);
        files.set(file.repository_id + '/' + file.path, {
          path: file.path,
          event,
          removed: file.operation === 'D'
        });
      }
    const entries = [...files.values()];
    this.label(
      `${entries.length} touched files · showing up to 250 · pan or zoom to explore`,
      25,
      28,
      '#94a3b8',
      650
    );
    if (!entries.length)
      this.label(
        'File history appears after a validated commit is available.',
        25,
        64,
        '#94a3b8',
        650
      );
    const groups = new Map<string, typeof entries>();
    for (const entry of entries.slice(0, 250)) {
      const repo = String(entry.event.payload.repository_id || '').slice(0, 8);
      const directory = `${repo} / ${entry.path.includes('/') ? entry.path.slice(0, entry.path.lastIndexOf('/')) : '/'}`;
      const group = groups.get(directory);
      if (group) group.push(entry);
      else groups.set(directory, [entry]);
    }
    let y = 62;
    for (const [directory, children] of groups) {
      this.label(directory, 25, y, '#c4b5fd', 300);
      children.forEach((entry, index) => {
        const x = 340 + (index % 3) * 200,
          cy = y - 10 + Math.floor(index / 3) * 35;
        const ctx = this.context!;
        ctx.strokeStyle = '#263b55';
        ctx.beginPath();
        ctx.moveTo(300, y - 4);
        ctx.lineTo(x, cy + 10);
        ctx.stroke();
        ctx.fillStyle = entry.removed ? '#fb7185' : '#67e8f9';
        ctx.fillRect(x, cy, 5, 22);
        this.label(
          entry.path.split('/').pop() || entry.path,
          x + 10,
          cy + 16,
          entry.removed ? '#fda4af' : '#e2e8f0',
          175
        );
        this.hits.push({ x, y: cy, width: 190, height: 26, event: entry.event });
      });
      y += 32 + Math.ceil(children.length / 3) * 35;
    }
  }
}
