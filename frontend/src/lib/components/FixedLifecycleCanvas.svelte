<script lang="ts">
  import { onMount } from 'svelte';
  import { operations, subscribeOperations } from '$lib/services/live-operations.svelte';
  import { bytes, count, duration, money } from './observability/format';
  import { resolve } from '$app/paths';
  import { Background, Controls, SvelteFlow } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';
  import { lifecycleEdges, lifecycleNodes } from '$lib/fixed-lifecycle';
  import { type EngineeringTask, type TeamActivity } from '$lib/services/engineering-v2';

  let { activity }: { activity: TeamActivity } = $props();
  let container: HTMLDivElement;
  let fullscreen = $state(false);
  let error = $state('');
  let selectedId = $state('');
  let selected = $derived(
    activity.tasks.find((task) => task.id === selectedId) ?? activity.tasks[0]
  );
  onMount(subscribeOperations);
  let nodes = $derived(
    lifecycleNodes(activity.tasks, selected).map((node) => {
      const runner = operations.live?.active_runners.find(
        (r) =>
          r.team_id === activity.team_id &&
          r.phase === node.id &&
          (!selected || r.task_id === selected.id)
      );
      const waiting = activity.tasks.find(
        (t) => t.stage === node.id && ['WAITING_HUMAN', 'WAITING_EXTERNAL'].includes(t.status ?? '')
      );
      const detail = runner
        ? `${runner.profile_name || runner.service_kind}\n${runner.task_key || runner.task_title || ''}\n${runner.harness || ''} ${runner.model || ''}\n${count(runner.input_tokens)} in · ${money(runner.known_cost_usd)}\nRAM ${bytes(runner.resources?.memory)} · ${duration(runner.wall_seconds)}`
        : waiting
          ? 'WAITING · AI spend while idle: $0'
          : '';
      return {
        ...node,
        data: { ...node.data, label: `${node.data.label}${detail ? '\n' + detail : ''}` },
        style: `${node.style || ''}; white-space: pre-line; width: 205px; font-size: 11px`
      };
    })
  );
  const describe = (task: EngineeringTask) => `${task.status} · ${task.stage}`;

  async function toggleFullscreen() {
    error = '';
    try {
      if (document.fullscreenElement === container) await document.exitFullscreen();
      else await container.requestFullscreen();
    } catch {
      error = 'Your browser could not enter fullscreen. Use its fullscreen command instead.';
    }
  }
</script>

<svelte:document
  onfullscreenchange={() => (fullscreen = document.fullscreenElement === container)}
/>
<div class="canvas" bind:this={container}>
  <header>
    <div>
      <h2>Fixed engineering lifecycle</h2>
      <p>Read-only map · planning and AI review are optional</p>
    </div>
    <button onclick={toggleFullscreen}>{fullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen'}</button
    >
  </header>
  {#if error}<p role="alert">{error}</p>{/if}
  <div class="workspace">
    <section class="map" aria-label="Lifecycle stages">
      <p class="guide">Intake → Developer → Validation → Publication → Review → Merge</p>
      <div class="flow">
        <SvelteFlow
          {nodes}
          edges={lifecycleEdges}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          deleteKey={null}
        >
          <Background />
          <Controls showLock={false} />
        </SvelteFlow>
      </div>
      <p>Planning is optional. Review waits use no AI. Fixes resume the same Developer session.</p>
    </section>
    <aside aria-label="Queue and task details">
      <h3>Queue and executing work</h3>
      {#each activity.tasks as task (task.id)}
        <button
          class="task"
          class:chosen={selected?.id === task.id}
          onclick={() => (selectedId = task.id)}
        >
          <span>{task.title}</span><small>P{task.priority} · {describe(task)}</small>
        </button>
      {:else}<p>No active or queued tasks.</p>{/each}
      {#if selected}
        <section class="details">
          <h3>Task details</h3>
          <p>{selected.title}</p>
          <p>{describe(selected)}</p>
          <p>Requirement version: {selected.requirement_version}</p>
          {#if selected.wait_reason && selected.wait_reason !== 'NONE'}<p>
              Waiting: {selected.wait_reason.replaceAll('_', ' ')}
            </p>{/if}
          <a href={resolve('/tasks/[id]', { id: selected.id })}>Open ticket →</a>
        </section>
      {/if}
      <h3>Recent milestones</h3>
      {#each activity.milestones.filter((item) => !selected || item.task_id === selected.id) as milestone (milestone.id)}
        <p class="milestone">
          <strong>{milestone.stage} · {milestone.status}</strong><br />
          {milestone.actor} ·
          <time datetime={milestone.started_at}
            >{new Date(milestone.started_at).toLocaleString()}</time
          >
        </p>
      {:else}<p>No milestones recorded yet.</p>{/each}
    </aside>
  </div>
</div>

<style>
  .canvas {
    border: 1px solid var(--color-line);
    border-radius: 16px;
    padding: 1rem;
    background:
      radial-gradient(
        circle at 100% 0%,
        color-mix(in srgb, var(--color-brand-2) 6%, transparent),
        transparent 50%
      ),
      var(--color-panel-alt);
    color: var(--color-text);
    box-shadow: 0 0 40px -22px color-mix(in srgb, var(--color-brand) 40%, transparent);
  }
  .canvas:fullscreen {
    border-radius: 0;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: auto;
    background: var(--color-panel-alt);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }
  h2,
  h3 {
    margin: 0.5rem 0;
  }
  h2 {
    font-size: 1.15rem;
    font-weight: 700;
    background-image: linear-gradient(90deg, var(--color-brand-2), var(--color-brand));
    background-clip: text;
    -webkit-background-clip: text;
    color: transparent;
  }
  h3 {
    color: var(--color-heading);
  }
  p {
    font-size: 0.85rem;
    color: var(--color-muted);
  }
  header p {
    margin: 0;
  }
  header button {
    border: 1px solid var(--color-brand);
    padding: 0.6rem 0.9rem;
    border-radius: 9px;
    background: color-mix(in srgb, var(--color-brand) 14%, var(--color-input));
    color: var(--color-text);
    cursor: pointer;
    font-weight: 600;
    white-space: nowrap;
    transition:
      box-shadow 0.25s var(--ease-smooth),
      transform 0.12s var(--ease-smooth);
  }
  header button:hover {
    box-shadow: 0 0 18px -4px color-mix(in srgb, var(--color-brand) 60%, transparent);
  }
  .workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
    gap: 1.5rem;
    min-height: 0;
    flex: 1;
  }
  .map {
    padding: 1rem;
    min-width: 0;
    border: 1px solid var(--color-line);
    border-radius: 12px;
    background: var(--color-panel);
  }
  .flow {
    height: 440px;
    min-height: 320px;
    border-radius: 10px;
    overflow: hidden;
  }
  .canvas:fullscreen .flow {
    height: calc(100dvh - 240px);
  }
  .guide {
    margin-bottom: 2rem;
    letter-spacing: 0.02em;
  }
  small {
    display: block;
    font-size: 0.75rem;
    opacity: 0.8;
    color: var(--color-muted);
  }
  aside {
    padding: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 12px;
    background: var(--color-panel);
    overflow: auto;
  }
  .task {
    width: 100%;
    text-align: left;
    margin-bottom: 0.5rem;
    border: 1px solid var(--color-line);
    padding: 0.65rem;
    border-radius: 9px;
    background: var(--color-input);
    color: var(--color-text);
    cursor: pointer;
    display: block;
    transition:
      border-color 0.25s var(--ease-smooth),
      box-shadow 0.25s var(--ease-smooth),
      transform 0.2s var(--ease-smooth);
  }
  .task:hover {
    border-color: color-mix(in srgb, var(--color-brand-2) 50%, var(--color-line));
    transform: translateX(2px);
  }
  .task.chosen {
    border-color: var(--color-brand);
    background: color-mix(in srgb, var(--color-brand) 12%, var(--color-input));
    box-shadow: 0 0 16px -4px color-mix(in srgb, var(--color-brand) 55%, transparent);
  }
  .details {
    padding: 1rem 0;
  }
  .milestone {
    padding-bottom: 0.7rem;
    border-bottom: 1px solid var(--color-line);
  }
  a {
    color: var(--color-brand-2);
  }
  a:hover {
    text-shadow: 0 0 10px color-mix(in srgb, var(--color-brand-2) 55%, transparent);
  }
  @media (max-width: 850px) {
    .workspace {
      grid-template-columns: 1fr;
    }
    aside {
      border-left: 0;
    }
  }

  /* Svelte Flow theming: bring the graph in line with the app's neon palette. */
  .flow :global(.svelte-flow) {
    --xy-background-color: transparent;
    --xy-background-pattern-color: color-mix(in srgb, var(--color-line) 90%, transparent);
    --xy-node-border: 1px solid var(--color-line);
    --xy-node-background-color: var(--color-panel);
    --xy-node-color: var(--color-text);
    --xy-node-border-radius: 10px;
    --xy-node-boxshadow-hover: 0 0 16px -4px color-mix(in srgb, var(--color-brand-2) 50%, transparent);
    --xy-node-boxshadow-selected: 0 0 0 1.5px var(--color-brand), 0 0 20px -2px
      color-mix(in srgb, var(--color-brand) 65%, transparent);
    --xy-edge-stroke: var(--color-brand-2);
    --xy-edge-stroke-width: 1.6;
    --xy-edge-stroke-selected: var(--color-brand);
    --xy-controls-button-background-color: var(--color-panel);
    --xy-controls-button-background-color-hover: color-mix(in srgb, var(--color-brand-2) 20%, var(--color-panel));
    --xy-controls-button-color: var(--color-text);
    --xy-controls-button-color-hover: var(--color-brand-2);
    --xy-controls-button-border-color: var(--color-line);
    --xy-controls-box-shadow: 0 0 14px -4px color-mix(in srgb, var(--color-brand-2) 40%, transparent);
    --xy-minimap-background-color: var(--color-panel);
  }
  .flow :global(.svelte-flow__node) {
    font-family: inherit;
    transition:
      box-shadow 0.25s var(--ease-smooth),
      border-color 0.25s var(--ease-smooth);
  }
  .flow :global(.svelte-flow__edge.animated path) {
    stroke-dasharray: 6;
    animation: dashdraw 0.9s linear infinite;
    filter: drop-shadow(0 0 4px color-mix(in srgb, var(--color-brand-2) 65%, transparent));
  }
  .flow :global(.svelte-flow__edge:hover .svelte-flow__edge-path) {
    stroke: var(--color-brand);
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--color-brand) 60%, transparent));
  }
  @media (prefers-reduced-motion: reduce) {
    .flow :global(.svelte-flow__edge.animated path) {
      animation: none;
    }
  }
</style>
