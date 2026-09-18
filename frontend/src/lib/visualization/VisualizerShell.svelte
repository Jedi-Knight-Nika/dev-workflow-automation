<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { activityApi } from './api';
  import { subscribeActivity } from './live-stream';
  import { createRenderer } from './renderer';
  import PreflightForm from './PreflightForm.svelte';
  import ActivityInspector from './ActivityInspector.svelte';
  import GourceReplay from './GourceReplay.svelte';
  import WorkPlanHistory from './WorkPlanHistory.svelte';
  import TaskDependencyHistory from './TaskDependencyHistory.svelte';
  import DeploymentSummary from '$lib/delivery/DeploymentSummary.svelte';
  import BottleneckSummary from './BottleneckSummary.svelte';
  import EconomicsSummary from './EconomicsSummary.svelte';
  import ProcessSummary from './ProcessSummary.svelte';
  import FileHistoryNotice from './FileHistoryNotice.svelte';
  import { ViewerMonitor } from './monitor';
  import { localDate, money, duration, title } from './format';
  import { compareActivity, gourceLog } from './replay';
  import type { ActivityEvent, Filters, Frame, Preflight, Scope, ViewMode } from './types';

  let { scope, onclose }: { scope: Scope; onclose: () => void } = $props();
  const initialScope = untrack(() => scope);
  let dialog: HTMLDialogElement, viewer: HTMLDivElement;
  let canvas = $state<HTMLCanvasElement>();
  let showAggregate = $state(false);
  let gourcePayload = $state<string | null>(null);
  let active = $state(false),
    busy = $state(false),
    error = $state(''),
    maximized = $state(false);
  let scopeChoice = $state(`${initialScope.type}:${initialScope.id || ''}`);
  let choices = $state([
    {
      value: `${initialScope.type}:${initialScope.id || ''}`,
      name: initialScope.type === 'workspace' ? 'Entire workspace' : `Current ${initialScope.type}`
    }
  ]);
  let from = $state(localDate(new Date(Date.now() - 86400000))),
    to = $state('');
  let detail = $state(2),
    mode = $state<ViewMode>(initialScope.type === 'workspace' ? 'workspace' : 'flow');
  let live = $state(false),
    connected = $state(false),
    realGaps = $state(false),
    speed = $state(1);
  let showCosts = $state(true),
    filters = $state<Filters>({ actor: '', kind: '', team: '', communication: true });
  let preflight = $state<Preflight | null>(null),
    frame = $state<Frame | null>(null);
  let events = $state<ActivityEvent[]>([]),
    generation = $state(0);
  let renderer: ReturnType<typeof createRenderer> | null = null;
  let unsubscribe: (() => void) | null = null;
  let resize: ResizeObserver | null = null;
  let flightRequest: AbortController | null = null,
    loadRequest: AbortController | null = null;
  let disposed = false,
    cursor = 0,
    wasPlaying = false;
  let drag: { x: number; y: number; moved: boolean } | null = null;
  const actors = $derived([...new Set(events.map((e) => e.actor))].sort());
  const kinds = $derived([...new Set(events.map((e) => e.kind))].sort());
  const teams = $derived([
    ...new Map(
      events.filter((e) => e.team_id).map((e) => [e.team_id!, e.team_name || 'Team'])
    ).entries()
  ]);
  const chronological = $derived([...events].sort(compareActivity));
  const recent = $derived(
    chronological.slice(Math.max(0, (frame?.index || 0) - 12), Math.max(12, frame?.index || 0))
  );
  const selected = $derived(frame?.selected ?? null);
  const sequences = $derived(new Set(events.map((event) => event.sequence)));
  let monitor: ViewerMonitor | null = null;
  function seek(sequence: number) {
    renderer?.send({
      type: 'SEEK',
      index: chronological.findIndex((event) => event.sequence === sequence) + 1
    });
  }

  function selection(): Scope {
    const divider = scopeChoice.indexOf(':');
    return {
      type: scopeChoice.slice(0, divider) as Scope['type'],
      id: scopeChoice.slice(divider + 1) || null
    };
  }
  async function check() {
    if (to) live = false;
    if (detail === 1 && mode === 'code') mode = 'flow';
    flightRequest?.abort();
    const request = new AbortController();
    flightRequest = request;
    preflight = null;
    showAggregate = false;
    error = '';
    busy = true;
    try {
      const next = await activityApi.preflight(
        selection(),
        new Date(from).toISOString(),
        to ? new Date(to).toISOString() : null,
        detail,
        request.signal
      );
      if (!disposed && !request.signal.aborted) preflight = next;
    } catch (cause) {
      if (!disposed && !request.signal.aborted)
        error = cause instanceof Error ? cause.message : 'Could not load activity.';
    } finally {
      if (!disposed && !request.signal.aborted) busy = false;
    }
  }
  function stopStream() {
    unsubscribe?.();
    unsubscribe = null;
    connected = false;
  }
  function stopView() {
    gourcePayload = null;
    stopStream();
    monitor?.dispose();
    monitor = null;
    resize?.disconnect();
    resize = null;
    renderer?.dispose();
    renderer = null;
    loadRequest?.abort();
  }
  function connect() {
    stopStream();
    if (!live || !preflight || document.hidden || disposed || gourcePayload !== null) return;
    unsubscribe = subscribeActivity({
      preflight,
      detail,
      after: cursor,
      events,
      connection: (value) => {
        connected = value;
      },
      reconnect: () => monitor?.reconnect(),
      cursor: (value) => {
        cursor = value;
      },
      status: (value) => {
        preflight = value;
      },
      capacity: (evidence) => renderer?.send({ type: 'CAPACITY', evidence }),
      append: (item, nextEvents, nextPreflight) => {
        events = nextEvents;
        preflight = nextPreflight;
        renderer?.send({ type: 'APPEND', events: [item] });
      },
      error: (message, pause) => {
        if (pause) renderer?.send({ type: 'PAUSE' });
        error = message;
      }
    });
  }
  async function start() {
    // Workers require plain data; nested Svelte state proxies cannot be transferred.
    const flight = $state.snapshot(preflight);
    if (!flight || flight.too_large) return;
    stopView();
    error = '';
    busy = true;
    const request = new AbortController();
    loadRequest = request;
    try {
      const data = await activityApi.load(flight, detail, request.signal);
      if (disposed || request.signal.aborted) return;
      events = data.events;
      cursor = flight.through_sequence;
      frame = null;
      active = true;
      generation += 1;
      await tick();
      if (disposed || request.signal.aborted || !canvas) return;
      monitor = new ViewerMonitor();
      renderer = createRenderer(
        canvas,
        {
          ...data,
          start: Date.parse(flight.from),
          mode,
          live,
          maxEvents: flight.max_events,
          maxTasks: flight.max_tasks,
          capacity: flight.capacity
        },
        (message) => {
          if (disposed || request.signal.aborted) return;
          monitor?.receive(message);
          if (message.type === 'FRAME') frame = message.frame;
          else {
            error = message.message;
            stopStream();
          }
        }
      );
      resize = new ResizeObserver(([entry]) =>
        renderer?.send({
          type: 'RESIZE',
          width: entry.contentRect.width,
          height: entry.contentRect.height,
          dpr: window.devicePixelRatio || 1
        })
      );
      resize.observe(canvas);
      renderer.send({ type: 'SPEED', speed, realGaps });
      renderer.send({ type: 'FILTER', filters: { ...filters } });
      if (live && !document.hidden) renderer.send({ type: 'PLAY' });
      connect();
    } catch (cause) {
      if (!disposed && !request.signal.aborted)
        error = cause instanceof Error ? cause.message : 'Activity could not be loaded.';
    } finally {
      if (!disposed && !request.signal.aborted) busy = false;
    }
  }
  async function reload() {
    stopView();
    active = false;
    await check();
  }
  function filter() {
    renderer?.send({ type: 'FILTER', filters: { ...filters } });
  }
  async function fullscreen() {
    if (document.fullscreenElement) {
      await document.exitFullscreen().catch(() => {});
      return;
    }
    if (viewer.requestFullscreen) {
      try {
        await viewer.requestFullscreen();
        return;
      } catch {
        /* viewport fallback */
      }
    }
    maximized = !maximized;
  }
  function download() {
    const url = URL.createObjectURL(new Blob([gourceLog(events)], { type: 'text/plain' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'engineering-activity.log';
    link.click();
    URL.revokeObjectURL(url);
  }
  function pointerDown(event: PointerEvent) {
    drag = { x: event.clientX, y: event.clientY, moved: false };
    canvas?.setPointerCapture(event.pointerId);
  }
  function pointerMove(event: PointerEvent) {
    if (!drag) return;
    const x = event.clientX - drag.x,
      y = event.clientY - drag.y;
    if (Math.abs(x) + Math.abs(y) > 2) drag.moved = true;
    renderer?.send({ type: 'PAN', x, y });
    drag.x = event.clientX;
    drag.y = event.clientY;
  }
  function pointerUp(event: PointerEvent) {
    if (drag && !drag.moved && canvas) {
      const rect = canvas.getBoundingClientRect();
      renderer?.send({ type: 'SELECT', x: event.clientX - rect.left, y: event.clientY - rect.top });
    }
    drag = null;
  }
  onMount(() => {
    dialog.showModal();
    void check();
    const request = new AbortController();
    void activityApi
      .scopes(request.signal)
      .then((result) => {
        if (disposed) return;
        choices = [
          ...new Map(
            [
              ...choices,
              { value: 'workspace:', name: 'Entire workspace' },
              ...result.projects.map((item) => ({
                value: `project:${item.id}`,
                name: `Project · ${item.name}`
              })),
              ...result.teams.map((item) => ({
                value: `team:${item.id}`,
                name: `Team · ${item.name}`
              })),
              ...result.repositories.map((item) => ({
                value: `repository:${item.id}`,
                name: `Repository · ${item.name}`
              }))
            ].map((item) => [item.value, item])
          ).values()
        ];
      })
      .catch(() => {
        /* The current route scope remains usable if discovery fails. */
      });
    const visibility = () => {
      if (document.hidden) {
        wasPlaying = !!frame?.playing;
        renderer?.send({ type: 'PAUSE' });
        stopStream();
      } else {
        if (wasPlaying) renderer?.send({ type: 'PLAY' });
        connect();
      }
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true;
      request.abort();
      flightRequest?.abort();
      stopView();
      document.removeEventListener('visibilitychange', visibility);
      dialog.close();
    };
  });
</script>

<dialog
  bind:this={dialog}
  class:active
  class:maximized
  aria-labelledby="activity-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
>
  <div class="viewer" bind:this={viewer}>
    <header>
      <div>
        <p class="eyebrow">ENGINEERING OBSERVATORY</p>
        <h2 id="activity-title">Activity replay</h2>
      </div>
      <div class="window-actions">
        {#if active}<button onclick={() => (maximized = !maximized)}
            >{maximized ? 'Restore window' : 'Maximize'}</button
          ><button onclick={fullscreen}>Fullscreen activity</button>{/if}
        <button class="close" aria-label="Close activity visualization" onclick={onclose}>✕</button>
      </div>
    </header>
    {#if error}<div class="notice error" role="alert">
        {error}
        {#if active}<button onclick={reload}>Reload view</button>{/if}
      </div>{/if}
    {#if !active}
      <PreflightForm
        bind:scopeChoice
        {choices}
        bind:from
        bind:to
        bind:detail
        bind:mode
        bind:live
        bind:showAggregate
        {preflight}
        {busy}
        oncheck={check}
        onstart={start}
        {onclose}
      />
    {:else}
      {#if preflight?.delayed}<p class="notice">
          Activity history is catching up or the projector is unavailable. This view may be
          incomplete.
        </p>{/if}
      <FileHistoryNotice history={preflight?.file_history} />
      <div class="toolbar" aria-label="Visualization controls">
        <button
          class="primary"
          onclick={() => renderer?.send({ type: frame?.playing ? 'PAUSE' : 'PLAY' })}
          >{frame?.playing ? 'Pause' : live ? 'Follow live' : 'Play'}</button
        >
        <select
          aria-label="Playback speed"
          bind:value={speed}
          onchange={() => renderer?.send({ type: 'SPEED', speed, realGaps })}
          >{#each [0.5, 1, 2, 5, 10] as value (value)}<option {value}>{value}×</option
            >{/each}</select
        >
        <select
          aria-label="Visualization view"
          bind:value={mode}
          onchange={() => renderer?.send({ type: 'MODE', mode })}
          ><option value="flow">Flow</option><option value="workspace">Workspace</option><option
            value="code"
            disabled={detail === 1}>Code</option
          ></select
        >
        <label class="check"
          ><input
            type="checkbox"
            bind:checked={realGaps}
            onchange={() => renderer?.send({ type: 'SPEED', speed, realGaps })}
          /> Real time gaps</label
        >
        <button onclick={() => renderer?.send({ type: 'RESET_CAMERA' })}>Reset camera</button>
        <button onclick={reload}>Change scope</button>
        <span class:connected class="connection"
          >{live ? (connected ? '● Live' : '○ Reconnecting') : 'Historical replay'}</span
        >
      </div>
      <div class="filters">
        <select aria-label="Filter actor" bind:value={filters.actor} onchange={filter}
          ><option value="">All actors</option>{#each actors as actor (actor)}<option
              >{actor}</option
            >{/each}</select
        >
        <select aria-label="Filter event type" bind:value={filters.kind} onchange={filter}
          ><option value="">All events</option>{#each kinds as kind (kind)}<option value={kind}
              >{title(kind)}</option
            >{/each}</select
        >
        <select aria-label="Filter team" bind:value={filters.team} onchange={filter}
          ><option value="">All Teams</option>{#each teams as [id, name] (id)}<option value={id}
              >{name}</option
            >{/each}</select
        >
        <label class="check"
          ><input type="checkbox" bind:checked={filters.communication} onchange={filter} /> Communication</label
        >
        <label class="check"><input type="checkbox" bind:checked={showCosts} /> Usage</label>
      </div>
      <div class="canvas-wrap">
        {#key generation}<canvas
            bind:this={canvas}
            aria-label="Engineering activity diagram. Arrow keys pan, plus and minus zoom; the timeline below selects events."
            tabindex="0"
            onkeydown={(event) => {
              const movement: Record<string, [number, number]> = {
                ArrowLeft: [30, 0],
                ArrowRight: [-30, 0],
                ArrowUp: [0, 30],
                ArrowDown: [0, -30]
              };
              if (movement[event.key]) {
                event.preventDefault();
                const [x, y] = movement[event.key];
                renderer?.send({ type: 'PAN', x, y });
              } else if (['+', '-', '='].includes(event.key)) {
                event.preventDefault();
                renderer?.send({ type: 'ZOOM', factor: event.key === '-' ? 0.89 : 1.12 });
              }
            }}
            onpointerdown={pointerDown}
            onpointermove={pointerMove}
            onpointerup={pointerUp}
            onpointercancel={() => (drag = null)}
            onwheel={(event) => {
              event.preventDefault();
              renderer?.send({ type: 'ZOOM', factor: event.deltaY < 0 ? 1.12 : 0.89 });
            }}
          ></canvas>{/key}
        <div class="legend">
          <span>● Agent</span><span>● Human</span><span>● System</span><span>● Integration</span
          ><span>Amber: waiting · Red: failed</span>
        </div>
      </div>
      <div class="timeline">
        <button
          aria-label="Previous activity event"
          onclick={() => renderer?.send({ type: 'SEEK', index: (frame?.index || 0) - 1 })}>‹</button
        ><input
          aria-label="Activity timeline"
          type="range"
          min="0"
          max={frame?.count || 0}
          value={frame?.index || 0}
          oninput={(event) =>
            renderer?.send({ type: 'SEEK', index: Number(event.currentTarget.value) })}
        /><button
          aria-label="Next activity event"
          onclick={() => renderer?.send({ type: 'SEEK', index: (frame?.index || 0) + 1 })}>›</button
        ><time>{frame ? new Date(frame.at).toLocaleString() : 'Loading…'}</time><span
          >{frame?.index || 0} / {frame?.count || 0}</span
        >
      </div>
      <div class="details">
        <section class="history" aria-label="Activity event list">
          <h3>Recorded events</h3>
          {#each recent as event (event.sequence)}<button
              class:selected={selected?.sequence === event.sequence}
              onclick={() =>
                renderer?.send({
                  type: 'SEEK',
                  index: chronological.findIndex((e) => e.sequence === event.sequence) + 1
                })}
              ><time>{new Date(event.occurred_at).toLocaleTimeString()}</time><span
                >{title(event.kind)}</span
              ><small>{event.actor} · {event.task_key || event.task_title}</small></button
            >{:else}<p>No events in this selection.</p>{/each}
        </section>
        {#if preflight}<ActivityInspector
            {selected}
            flight={preflight}
            {detail}
            {sequences}
            events={chronological}
            onseek={seek}
          />{/if}
      </div>
      {#if frame}<div class="metrics">
          <details class="border-t border-line px-4 py-2 text-xs">
            <summary class="cursor-pointer">Deployment summary</summary><DeploymentSummary
              metrics={frame.deployments}
            />
          </details>
          <ProcessSummary metrics={frame.process} /><TaskDependencyHistory
            tasks={frame.tasks}
          /><WorkPlanHistory snapshots={frame.workPlans} /><BottleneckSummary
            values={frame.bottlenecks}
            {live}
          />{#if showCosts}<EconomicsSummary economics={frame.economics} />{/if}
        </div>{/if}
      {#if gourcePayload !== null}<GourceReplay
          log={gourcePayload}
          onerror={() => monitor?.gourceFailure()}
          onclose={() => {
            gourcePayload = null;
            connect();
          }}
        />{/if}
      <footer class="summary">
        {#if frame}<span
            >Recorded task time: <b>{duration(frame.activeMs)}</b> active ·
            <b>{duration(frame.waitingMs)}</b> waiting</span
          >{#if showCosts}<span
              >Window receipts: <b>{money(frame.cost)}</b>{frame.unknownCosts
                ? ` + ${frame.unknownCosts} unknown`
                : ''} · {frame.inputTokens.toLocaleString()} in / {frame.outputTokens.toLocaleString()}
              out{frame.incompleteUsage ? ` (${frame.incompleteUsage} partial usage)` : ''}</span
            >{/if}{/if}
        {#if mode === 'code'}<button
            disabled={!events.some((event) => event.files.length)}
            onclick={() => {
              renderer?.send({ type: 'PAUSE' });
              stopStream();
              gourcePayload = gourceLog(events);
            }}>Open Gource replay</button
          ><button disabled={!events.some((event) => event.files.length)} onclick={download}
            >Export Gource log</button
          >{/if}
      </footer>
    {/if}
  </div>
</dialog>

<style>
  dialog {
    position: fixed;
    inset: 0;
    width: min(680px, calc(100vw - 2rem));
    max-width: none;
    max-height: calc(100dvh - 2rem);
    padding: 0;
    margin: auto;
    border: 1px solid var(--color-line);
    border-radius: 14px;
    background: var(--color-panel);
    color: var(--color-text);
    box-shadow: 0 30px 100px #0009;
    overflow: auto;
  }
  dialog::backdrop {
    background: #020617b8;
    backdrop-filter: blur(5px);
  }
  dialog.active {
    width: min(1360px, calc(100vw - 2rem));
    height: min(940px, calc(100dvh - 2rem));
    resize: both;
    min-width: min(620px, 100vw);
    min-height: min(580px, 100dvh);
    overflow: hidden;
  }
  dialog.maximized {
    width: 100vw;
    height: 100dvh;
    max-height: 100dvh;
    border-radius: 0;
  }
  .viewer {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background: var(--color-panel);
  }
  .viewer:fullscreen {
    width: 100vw;
    height: 100dvh;
    padding: 0;
  }
  header,
  .toolbar,
  .filters,
  .window-actions,
  header {
    justify-content: space-between;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--color-line);
  }
  h2 {
    margin: 0;
    font-size: 1.1rem;
    color: var(--color-heading);
  }
  h3 {
    font-size: 0.85rem;
    text-transform: capitalize;
    color: var(--color-heading);
    margin: 0 0 0.65rem;
  }
  .eyebrow {
    margin: 0 0 0.25rem;
    font-size: 0.58rem;
    letter-spacing: 0.2em;
    color: var(--color-brand-2);
  }
  button,
  select,
  input:not([type='checkbox']):not([type='range']) {
    border: 1px solid var(--color-line);
    border-radius: 7px;
    background: var(--color-panel-alt);
    color: var(--color-heading);
    padding: 0.45rem 0.65rem;
    font-size: 0.77rem;
  }
  button {
    cursor: pointer;
  }
  button:hover,
  button:focus-visible {
    border-color: var(--color-brand-2);
  }
  button:disabled {
    opacity: 0.45;
    cursor: default;
  }
  button.primary {
    background: var(--color-brand-2);
    border-color: transparent;
    color: #06121a;
    font-weight: 650;
  }
  .close {
    font-size: 1rem;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin: 0.85rem 0;
    font-size: 0.8rem;
  }
  .check {
    display: inline-flex;
    flex-direction: row;
    align-items: center;
    margin: 0;
    white-space: nowrap;
    gap: 0.35rem;
    font-size: 0.75rem;
  }
  input[type='checkbox'] {
    accent-color: var(--color-brand-2);
  }
  small {
    color: var(--color-muted);
    font-size: 0.73rem;
  }
  .notice {
    padding: 0.7rem 1rem;
    font-size: 0.8rem;
    color: var(--color-warning);
    background: color-mix(in srgb, var(--color-warning) 8%, transparent);
  }
  .notice.error {
    color: var(--color-danger);
    flex-shrink: 0;
  }
  .notice button {
    margin-left: 0.7rem;
  }
  .toolbar,
  .filters {
    flex-wrap: wrap;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--color-line);
    flex-shrink: 0;
  }
  .connection {
    margin-left: auto;
    font-size: 0.73rem;
    color: var(--color-muted);
  }
  .connection.connected {
    color: #34d399;
  }
  .canvas-wrap {
    flex: 1 1 40%;
    min-height: 80px;
    position: relative;
    overflow: hidden;
  }
  canvas {
    width: 100%;
    height: 100%;
    display: block;
    touch-action: none;
    cursor: grab;
  }
  canvas:active {
    cursor: grabbing;
  }
  .legend {
    position: absolute;
    pointer-events: none;
    left: 0.8rem;
    bottom: 0.6rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
    padding: 0.35rem 0.6rem;
    background: #080e1be8;
    font-size: 0.64rem;
    color: #94a3b8;
  }
  .legend span:nth-child(1) {
    color: #67e8f9;
  }
  .legend span:nth-child(2) {
    color: #f9a8d4;
  }
  .legend span:nth-child(3) {
    color: #cbd5e1;
  }
  .legend span:nth-child(4) {
    color: #c4b5fd;
  }
  .timeline {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.65rem 1rem;
    border-top: 1px solid var(--color-line);
    border-bottom: 1px solid var(--color-line);
    font-size: 0.7rem;
    flex-shrink: 0;
  }
  .timeline input {
    flex: 1;
    min-width: 40px;
    accent-color: var(--color-brand-2);
  }
  .timeline time {
    min-width: 140px;
  }
  .details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    min-height: 80px;
    max-height: 28%;
    flex: 0 1 220px;
  }
  .metrics {
    flex-shrink: 0;
    max-height: 25%;
    overflow: auto;
  }
  .history {
    overflow: auto;
    padding: 0.9rem 1rem;
    font-size: 0.78rem;
  }
  .history {
    border-right: 1px solid var(--color-line);
  }
  .history button {
    width: 100%;
    display: grid;
    grid-template-columns: 70px 1fr;
    text-align: left;
    gap: 0.2rem 0.5rem;
    margin: 0.25rem 0;
    border-color: transparent;
    background: transparent;
  }
  .history button.selected {
    border-color: var(--color-brand-2);
    background: var(--color-panel-alt);
  }
  .history small {
    grid-column: 2;
  }
  .history span {
    text-transform: capitalize;
  }
  .summary {
    flex-wrap: wrap;
    justify-content: space-between;
    border-top: 1px solid var(--color-line);
    padding: 0.6rem 1rem;
    font-size: 0.7rem;
    flex-shrink: 0;
    color: var(--color-muted);
  }
  .summary b {
    color: var(--color-heading);
  }
  @media (max-width: 700px) {
    dialog.active {
      width: 100vw;
      height: 100dvh;
      max-height: 100dvh;
      border-radius: 0;
    }
    .window-actions {
      gap: 0.25rem;
    }
    .window-actions button:not(.close) {
      font-size: 0.65rem;
      padding: 0.3rem;
    }
    .details {
      grid-template-columns: 1fr;
    }
    .history {
      display: none;
    }
    .timeline time {
      min-width: 0;
      max-width: 100px;
    }
    .connection {
      margin-left: 0;
    }
  }
</style>
