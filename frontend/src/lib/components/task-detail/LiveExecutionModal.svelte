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
  let position = $state({ x: 0, y: 0 });
  let drag = $state<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);

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

  function startDrag(event: PointerEvent) {
    if (
      event.pointerType !== 'mouse' ||
      event.button !== 0 ||
      (event.target instanceof Element && event.target.closest('button'))
    )
      return;
    const bounds = dialog.getBoundingClientRect();
    drag = {
      pointerId: event.pointerId,
      offsetX: event.clientX - bounds.left,
      offsetY: event.clientY - bounds.top
    };
    dialog.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function moveDrag(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const bounds = dialog.getBoundingClientRect();
    position = {
      x: Math.max(0, Math.min(window.innerWidth - bounds.width, event.clientX - drag.offsetX)),
      y: Math.max(0, Math.min(window.innerHeight - bounds.height, event.clientY - drag.offsetY))
    };
  }

  function finishDrag(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    drag = null;
    if (dialog.hasPointerCapture(event.pointerId)) dialog.releasePointerCapture(event.pointerId);
  }

  onMount(() => {
    dialog.showModal();
    void tick().then(() => {
      const bounds = dialog.getBoundingClientRect();
      position = { x: bounds.left, y: bounds.top };
    });
    void push('Opening bounded execution telemetry…');
    void poll();
    const timer = setInterval(() => {
      if (!document.hidden) void poll();
    }, 2500);
    return () => clearInterval(timer);
  });
</script>

<dialog
  bind:this={dialog}
  style:left={`${position.x}px`}
  style:top={`${position.y}px`}
  onclose={onClose}
  onclick={(event) => {
    if (event.target === dialog) dialog.close();
  }}
>
  <section>
    <header
      role="presentation"
      class:dragging={drag !== null}
      onpointerdown={startDrag}
      onpointermove={moveDrag}
      onpointerup={finishDrag}
      onpointercancel={finishDrag}
    >
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
  </section>
</dialog>

<style>
  dialog {
    position: fixed;
    width: min(900px, calc(100vw - 2rem));
    height: min(600px, calc(100dvh - 2rem));
    min-width: min(320px, calc(100vw - 2rem));
    min-height: 280px;
    max-width: calc(100vw - 2rem);
    max-height: calc(100dvh - 2rem);
    margin: 0;
    resize: both;
    border: 1px solid color-mix(in srgb, #22d3ee 48%, var(--color-line));
    border-radius: 15px;
    padding: 0;
    overflow: hidden;
    background: #070b12;
    color: #d8fdf7;
    box-shadow: 0 0 80px -20px #22d3ee88;
  }
  dialog::backdrop {
    background: rgb(2 6 15 / 76%);
    backdrop-filter: blur(8px);
  }
  section {
    min-height: 0;
    height: 100%;
    display: grid;
    grid-template-rows: auto 1fr auto;
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
  header.dragging {
    cursor: grabbing;
  }
  footer {
    padding: 0.65rem 1rem;
    border-top: 1px solid #243140;
    color: #71889a;
    font:
      0.62rem ui-monospace,
      monospace;
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
    min-height: 0;
    overflow: auto;
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
