<script lang="ts">
  import { onMount, tick } from 'svelte';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';
  import { getLiveExecution } from '$lib/services/tasks';
  import type { LiveExecution } from '$lib/types';

  let { taskId, title, onClose }: { taskId: string; title: string; onClose: () => void } = $props();
  let dialog: HTMLDialogElement;
  let terminal: HTMLDivElement;
  let lines = $state<string[]>([]);
  let activeRun = $state<LiveExecution | null>(null);
  let previous: LiveExecution['telemetry'] = null;
  let connected = $state(false);
  const minimumWidth = 360;
  const minimumHeight = 430;
  let layout = $state<{ x: number; y: number; width: number; height: number } | null>(null);
  let interaction: {
    type: 'drag' | 'resize';
    pointerX: number;
    pointerY: number;
    layout: { x: number; y: number; width: number; height: number };
  } | null = null;

  const stamp = () => new Date().toLocaleTimeString([], { hour12: false });
  const push = async (message: string) => {
    lines = [...lines.slice(-199), `[${stamp()}] ${message}`];
    await tick();
    if (terminal) terminal.scrollTop = terminal.scrollHeight;
  };

  function number(value: number | null | undefined) {
    return value === null || value === undefined ? 'unavailable' : value.toLocaleString();
  }

  async function poll() {
    try {
      const run = await getLiveExecution(taskId);
      if (!run) {
        if (!connected) await push('No AI execution receipt is available yet.');
        connected = true;
        return;
      }
      if (!activeRun || activeRun.id !== run.id) {
        activeRun = run;
        previous = null;
        await push(`Attached read-only · ${run.provider}/${run.model} · ${run.harness || 'API'}`);
      }
      const next = run.telemetry;
      if (next) {
        if (next.phase_label && next.phase_label !== previous?.phase_label)
          await push(`Phase → ${next.phase_label.replaceAll('_', ' ').toLowerCase()}`);
        if ((next.source_read_count ?? 0) > (previous?.source_read_count ?? 0))
          await push(`Source inspection · ${next.source_read_count} bounded reads total`);
        if ((next.tool_call_count ?? 0) > (previous?.tool_call_count ?? 0))
          await push(`Tool completed · ${next.tool_call_count} calls total`);
        if ((next.diff_changes ?? 0) > (previous?.diff_changes ?? 0))
          await push(`Workspace diff advanced · ${next.diff_changes} useful changes observed`);
        if ((next.targeted_check_improvements ?? 0) > (previous?.targeted_check_improvements ?? 0))
          await push('Targeted check improved');
        for (const warning of next.warnings ?? []) {
          if (!previous?.warnings?.includes(warning)) await push(`Policy signal · ${warning}`);
        }
        if (next.stop_reason && next.stop_reason !== previous?.stop_reason)
          await push(`Execution stopped safely · ${next.stop_reason}`);
        if (next.input_tokens_observed !== previous?.input_tokens_observed)
          await push(
            `Usage observed · ${number(next.input_tokens_observed)} input · ${number(next.active_context_estimate)} active context`
          );
      }
      if (run.status !== activeRun.status) await push(`Run status → ${run.status.toLowerCase()}`);
      activeRun = run;
      previous = next ? structuredClone(next) : null;
      connected = true;
    } catch {
      if (connected) await push('Telemetry connection interrupted · retrying');
      connected = false;
    }
  }

  function clamp(value: number, minimum: number, maximum: number) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function fitInViewport(next: { x: number; y: number; width: number; height: number }) {
    const maximumWidth = window.innerWidth;
    const maximumHeight = window.innerHeight;
    const width = clamp(next.width, Math.min(minimumWidth, maximumWidth), maximumWidth);
    const height = clamp(next.height, Math.min(minimumHeight, maximumHeight), maximumHeight);
    return {
      x: clamp(next.x, 0, Math.max(0, maximumWidth - width)),
      y: clamp(next.y, 0, Math.max(0, maximumHeight - height)),
      width,
      height
    };
  }

  function currentLayout() {
    if (layout) return fitInViewport(layout);
    const rect = dialog.getBoundingClientRect();
    return fitInViewport({ x: rect.left, y: rect.top, width: rect.width, height: rect.height });
  }

  function fitWindowInViewport() {
    if (layout) layout = fitInViewport(layout);
  }

  function endInteraction() {
    interaction = null;
    window.removeEventListener('pointermove', moveWindow);
    window.removeEventListener('pointerup', endInteraction);
    window.removeEventListener('pointercancel', endInteraction);
  }

  function moveWindow(event: PointerEvent) {
    if (!interaction) return;
    const deltaX = event.clientX - interaction.pointerX;
    const deltaY = event.clientY - interaction.pointerY;
    const initial = interaction.layout;

    if (interaction.type === 'drag') {
      layout = fitInViewport({
        ...initial,
        x: initial.x + deltaX,
        y: initial.y + deltaY
      });
    } else {
      layout = fitInViewport({
        ...initial,
        width: initial.width + deltaX,
        height: initial.height + deltaY
      });
    }
  }

  function beginInteraction(event: PointerEvent, type: 'drag' | 'resize') {
    if (event.button !== 0) return;
    event.preventDefault();
    interaction = {
      type,
      pointerX: event.clientX,
      pointerY: event.clientY,
      layout: currentLayout()
    };
    window.addEventListener('pointermove', moveWindow);
    window.addEventListener('pointerup', endInteraction);
    window.addEventListener('pointercancel', endInteraction);
  }

  function beginDrag(event: PointerEvent) {
    if (event.target instanceof Element && event.target.closest('button')) return;
    beginInteraction(event, 'drag');
  }

  function resizeWithKeyboard(event: KeyboardEvent) {
    const increment = event.shiftKey ? 40 : 10;
    const changes: Record<string, { width?: number; height?: number }> = {
      ArrowRight: { width: increment },
      ArrowLeft: { width: -increment },
      ArrowDown: { height: increment },
      ArrowUp: { height: -increment }
    };
    const change = changes[event.key];
    if (!change) return;
    event.preventDefault();
    const current = currentLayout();
    layout = fitInViewport({
      ...current,
      width: current.width + (change.width ?? 0),
      height: current.height + (change.height ?? 0)
    });
  }

  onMount(() => {
    dialog.showModal();
    requestAnimationFrame(() => {
      const rect = dialog.getBoundingClientRect();
      layout = fitInViewport({ x: rect.left, y: rect.top, width: rect.width, height: rect.height });
    });
    window.addEventListener('resize', fitWindowInViewport);
    void push('Opening bounded execution telemetry…');
    void poll();
    const timer = setInterval(() => {
      if (!document.hidden) void poll();
    }, 2500);
    return () => {
      clearInterval(timer);
      endInteraction();
      window.removeEventListener('resize', fitWindowInViewport);
    };
  });
</script>

<dialog
  bind:this={dialog}
  style={layout
    ? `left: ${layout.x}px; top: ${layout.y}px; width: ${layout.width}px; height: ${layout.height}px; transform: none`
    : ''}
  onclose={onClose}
  onclick={(event) => {
    if (event.target === dialog) dialog.close();
  }}
>
  <section>
    <header onpointerdown={beginDrag}>
      <div class="identity">
        <span class:connected class="live-dot"></span>
        <BrandIcon brand={activeRun?.provider || 'ai'} size={19} />
        <div>
          <small>LIVE EXECUTION · READ ONLY</small>
          <h2>{title}</h2>
        </div>
      </div>
      <button onclick={() => dialog.close()} aria-label="Close live execution">×</button>
    </header>
    <div class="terminal" bind:this={terminal} role="log" aria-live="polite">
      {#each lines as line, index (`${index}-${line}`)}<p><span>›</span> {line}</p>{/each}
      {#if activeRun?.status === 'RUNNING'}<p class="cursor">
          <span>›</span> waiting for next runtime signal <i></i>
        </p>{/if}
    </div>
    <footer>
      <span>{activeRun ? `${activeRun.provider} · ${activeRun.model}` : 'Awaiting run'}</span>
      <span>Bounded telemetry only · no prompts, source, or credentials</span>
    </footer>
    <button
      type="button"
      class="resize-handle"
      aria-label="Resize live execution window"
      onpointerdown={(event) => beginInteraction(event, 'resize')}
      onkeydown={resizeWithKeyboard}
    ></button>
  </section>
</dialog>

<style>
  dialog {
    --minimum-window-height: min(430px, 100dvh);
    width: min(900px, calc(100vw - 2rem));
    max-width: none;
    box-sizing: border-box;
    position: fixed;
    margin: 0;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    border: 1px solid color-mix(in srgb, #22d3ee 48%, var(--color-line));
    border-radius: 15px;
    padding: 0;
    overflow: hidden;
    min-width: min(360px, 100vw);
    min-height: var(--minimum-window-height);
    background: #070b12;
    color: #d8fdf7;
    box-shadow: 0 0 80px -20px #22d3ee88;
  }
  dialog::backdrop {
    background: rgb(2 6 15 / 76%);
    backdrop-filter: blur(8px);
  }
  section {
    box-sizing: border-box;
    min-height: var(--minimum-window-height);
    display: grid;
    grid-template-rows: auto 1fr auto;
    height: 100%;
  }
  header,
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border-color: #243140;
    background: #0c121d;
  }
  header {
    padding: 0.9rem 1rem;
    border-bottom: 1px solid #243140;
    cursor: grab;
    user-select: none;
  }
  footer {
    padding: 0.65rem 1rem;
    border-top: 1px solid #243140;
    color: #71889a;
    font:
      0.62rem ui-monospace,
      monospace;
  }
  header:active {
    cursor: grabbing;
  }
  .identity {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    min-width: 0;
  }
  h2 {
    margin: 0.1rem 0 0;
    overflow: hidden;
    color: #eafffb;
    font-size: 0.9rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  small {
    color: #5eead4;
    font:
      0.58rem ui-monospace,
      monospace;
    letter-spacing: 0.13em;
  }
  header button {
    border: 1px solid #2b3a49;
    border-radius: 7px;
    width: 32px;
    height: 32px;
    background: #111a26;
    color: #a9bbc8;
    cursor: pointer;
    font-size: 1.25rem;
  }
  header button:hover {
    border-color: #22d3ee;
    color: white;
  }
  .live-dot {
    width: 9px;
    height: 9px;
    flex: none;
    border-radius: 50%;
    background: #64748b;
  }
  .live-dot.connected {
    background: #34d399;
    box-shadow: 0 0 12px #34d399;
    animation: pulse 1.4s ease-in-out infinite;
  }
  .terminal {
    max-height: none;
    overflow: auto;
    min-height: 0;
    padding: 1rem 1.1rem;
    background:
      radial-gradient(circle at 100% 0, #08334444, transparent 45%),
      repeating-linear-gradient(0deg, transparent 0 22px, #ffffff05 23px), #070b12;
    scrollbar-color: #253747 transparent;
  }
  p {
    margin: 0 0 0.5rem;
    color: #a7c7c1;
    font:
      0.72rem/1.6 ui-monospace,
      SFMono-Regular,
      Menlo,
      monospace;
    white-space: pre-wrap;
  }
  p span {
    color: #22d3ee;
  }
  .cursor i {
    display: inline-block;
    width: 7px;
    height: 13px;
    margin-left: 0.3rem;
    vertical-align: -2px;
    background: #5eead4;
    animation: blink 1s steps(1) infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.4;
      transform: scale(0.72);
    }
  }
  @keyframes blink {
    50% {
      opacity: 0;
    }
  }
  .resize-handle {
    position: absolute;
    right: 0;
    bottom: 0;
    width: 22px;
    height: 22px;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: nwse-resize;
  }
  .resize-handle:focus-visible {
    outline: 2px solid #5eead4;
    outline-offset: -3px;
  }
  .resize-handle::after {
    content: '';
    position: absolute;
    right: 5px;
    bottom: 5px;
    width: 8px;
    height: 8px;
    border-right: 2px solid #5eead4;
    border-bottom: 2px solid #5eead4;
  }
  @media (max-height: 430px) {
    dialog {
      --minimum-window-height: 100dvh;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-dot.connected,
    .cursor i {
      animation: none;
    }
  }
  @media (max-width: 600px) {
    footer {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
