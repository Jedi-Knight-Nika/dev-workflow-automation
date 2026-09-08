<script lang="ts">
  import { onMount } from 'svelte';
  import { operations, subscribeOperations } from '$lib/services/live-operations.svelte';
  import { bytes, count, duration, money } from './observability/format';
  import { resolve } from '$app/paths';
  import { t } from '$lib/i18n/index.svelte';
  import { Background, Controls, MarkerType, SvelteFlow, type NodeTypes } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';
  import {
    lifecycleEdges,
    lifecycleNodes,
    type LifecycleNicknames,
    type LifecyclePositions
  } from '$lib/fixed-lifecycle';
  import { type EngineeringTask, type TeamActivity } from '$lib/services/engineering';
  import LifecycleNode from './LifecycleNode.svelte';
  import LiveExecutionModal from './task-detail/LiveExecutionModal.svelte';

  let { activity }: { activity: TeamActivity } = $props();
  let container: HTMLDivElement;
  let fullscreen = $state(false);
  let error = $state('');
  let selectedId = $state('');
  let savedPositions = $state<LifecyclePositions>({});
  let nicknames = $state<LifecycleNicknames>({});
  let liveExecution = $state<{ taskId: string; title: string } | null>(null);
  const nodeTypes: NodeTypes = { lifecycle: LifecycleNode };
  const storageKey = $derived(`engineering-canvas:${activity.team_id}`);
  let selected = $derived(
    activity.tasks.find((task) => task.id === selectedId) ?? activity.tasks[0]
  );
  onMount(() => {
    const unsubscribe = subscribeOperations();
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? '{}') as {
        positions?: LifecyclePositions;
        nicknames?: LifecycleNicknames;
      };
      savedPositions = saved.positions ?? {};
      nicknames = saved.nicknames ?? {};
    } catch {
      savedPositions = {};
      nicknames = {};
    }
    return unsubscribe;
  });

  function persistLayout(nextPositions = savedPositions, nextNicknames = nicknames) {
    localStorage.setItem(
      storageKey,
      JSON.stringify({ positions: nextPositions, nicknames: nextNicknames })
    );
  }

  function renameNode(id: string, nickname: string) {
    nicknames = { ...nicknames, [id]: nickname };
    persistLayout(savedPositions, nicknames);
  }

  function openLiveExecution(taskId: string, title: string) {
    liveExecution = { taskId, title };
  }

  function saveNodePosition(event: {
    targetNode: { id: string; position: { x: number; y: number } } | null;
  }) {
    if (!event.targetNode) return;
    savedPositions = {
      ...savedPositions,
      [event.targetNode.id]: { ...event.targetNode.position }
    };
    persistLayout(savedPositions, nicknames);
  }

  let nodes = $derived(
    lifecycleNodes(
      activity.tasks,
      selected,
      savedPositions,
      nicknames,
      renameNode,
      openLiveExecution
    ).map((node) => {
      const runner = operations.live?.active_runners.find(
        (r) =>
          r.team_id === activity.team_id &&
          r.phase === node.id &&
          (!selected || r.task_id === selected.id)
      );
      const waiting = activity.tasks.find(
        (t) => t.stage === node.id && ['WAITING_HUMAN', 'WAITING_EXTERNAL'].includes(t.status ?? '')
      );
      const aiStage = ['PLANNING', 'DEVELOPING', 'FIXING'].includes(node.id);
      const liveTaskId = aiStage
        ? (runner?.task_id ??
          activity.tasks.find((task) => task.stage === node.id && task.status === 'ACTIVE')?.id ??
          null)
        : null;
      const detail = runner
        ? `${runner.profile_name || runner.service_kind}\n${runner.task_key || runner.task_title || ''}\n${runner.harness || ''} ${runner.model || ''}\n${count(runner.input_tokens)} in · ${money(runner.known_cost_usd)}\nRAM ${bytes(runner.resources?.memory)} · ${duration(runner.wall_seconds)}`
        : waiting
          ? `${t('canvas.waitingIdleSpend')}`
          : '';
      return {
        ...node,
        data: {
          ...node.data,
          nickname: nicknames[node.id] ?? runner?.profile_name ?? node.data.nickname,
          detail,
          liveTaskId
        }
      };
    })
  );
  const activeStages = $derived(
    new Set(activity.tasks.filter((task) => task.status === 'ACTIVE').map((task) => task.stage))
  );
  let edges = $derived(
    lifecycleEdges.map((edge) => {
      const live = activeStages.has(edge.source) || activeStages.has(edge.target);
      return live
        ? {
            ...edge,
            animated: true,
            style: 'stroke: var(--color-brand-2); stroke-width: 2px;',
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 16,
              height: 16,
              color: 'var(--color-brand-2)'
            }
          }
        : edge;
    })
  );
  const describe = (task: EngineeringTask) => `${task.status} · ${task.stage}`;

  async function toggleFullscreen() {
    error = '';
    try {
      if (document.fullscreenElement === container) await document.exitFullscreen();
      else await container.requestFullscreen();
    } catch {
      error = t('canvas.fullscreenError');
    }
  }
</script>

<svelte:document
  onfullscreenchange={() => (fullscreen = document.fullscreenElement === container)}
/>
<div class="canvas" bind:this={container}>
  <header>
    <div>
      <h2>{t('canvas.title')}</h2>
      <p>{t('canvas.subtitle')}</p>
    </div>
    <button onclick={toggleFullscreen}
      >{fullscreen ? t('canvas.exitFullscreen') : t('canvas.fullscreen')}</button
    >
  </header>
  {#if error}<p role="alert">{error}</p>{/if}
  <div class="workspace">
    <section class="map" aria-label={t('canvas.lifecycleStages')}>
      <p class="guide">{t('canvas.guide')}</p>
      <div class="flow">
        <SvelteFlow
          {nodes}
          {edges}
          {nodeTypes}
          fitView
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          onnodedragstop={saveNodePosition}
          deleteKey={null}
        >
          <Background />
          <Controls showLock={false} />
        </SvelteFlow>
      </div>
      <p>{t('canvas.footnote')}</p>
    </section>
    <aside aria-label={t('canvas.queueAndDetails')}>
      <h3>{t('canvas.queueHeading')}</h3>
      {#each activity.tasks as task (task.id)}
        <button
          class="task"
          class:chosen={selected?.id === task.id}
          onclick={() => (selectedId = task.id)}
        >
          <span>{task.title}</span><small>P{task.priority} · {describe(task)}</small>
        </button>
      {:else}<p>{t('canvas.noTasks')}</p>{/each}
      {#if selected}
        <section class="details">
          <h3>{t('canvas.taskDetails')}</h3>
          <p>{selected.title}</p>
          <p>{describe(selected)}</p>
          <p>{t('canvas.requirementVersion', { version: selected.requirement_version })}</p>
          {#if selected.wait_reason && selected.wait_reason !== 'NONE'}<p>
              {t('canvas.waiting', { reason: selected.wait_reason.replaceAll('_', ' ') })}
            </p>{/if}
          <a href={resolve('/tasks/[id]', { id: selected.id })}>{t('canvas.openTicket')}</a>
        </section>
      {/if}
      <h3>{t('canvas.recentMilestones')}</h3>
      {#each activity.milestones.filter((item) => !selected || item.task_id === selected.id) as milestone (milestone.id)}
        <p class="milestone">
          <strong>{milestone.stage} · {milestone.status}</strong><br />
          {milestone.actor} ·
          <time datetime={milestone.started_at}
            >{new Date(milestone.started_at).toLocaleString()}</time
          >
        </p>
      {:else}<p>{t('canvas.noMilestones')}</p>{/each}
    </aside>
  </div>
</div>
{#if liveExecution}
  <LiveExecutionModal
    taskId={liveExecution.taskId}
    title={liveExecution.title}
    onClose={() => (liveExecution = null)}
  />
{/if}

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
    height: 560px;
    flex: 1;
  }
  .map {
    padding: 1rem;
    min-width: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--color-line);
    border-radius: 12px;
    background: var(--color-panel);
  }
  .flow {
    flex: 1;
    min-height: 0;
    border-radius: 10px;
    overflow: hidden;
  }
  .canvas:fullscreen .workspace {
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
    height: 100%;
    border: 1px solid var(--color-line);
    border-radius: 12px;
    background: var(--color-panel);
    overflow-y: auto;
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
      height: auto;
    }
    .map {
      height: 480px;
    }
    aside {
      height: auto;
      max-height: 420px;
      border-left: 0;
    }
  }

  /* Svelte Flow theming: bring the graph in line with the app's neon palette. */
  .flow :global(.svelte-flow) {
    --xy-background-color: transparent;
    --xy-background-pattern-color: color-mix(in srgb, var(--color-brand-2) 16%, var(--color-line));
    --xy-node-border: 1.5px solid color-mix(in srgb, var(--color-muted) 38%, var(--color-line));
    --xy-node-background-color: var(--color-panel);
    --xy-node-color: var(--color-heading);
    --xy-node-border-radius: 10px;
    --xy-node-boxshadow-hover: 0 0 16px -4px
      color-mix(in srgb, var(--color-brand-2) 55%, transparent);
    --xy-node-boxshadow-selected:
      0 0 0 1.5px var(--color-brand),
      0 0 20px -2px color-mix(in srgb, var(--color-brand) 65%, transparent);
    --xy-edge-stroke: color-mix(in srgb, var(--color-brand-2) 40%, var(--color-line));
    --xy-edge-stroke-width: 1.4;
    --xy-edge-stroke-selected: var(--color-brand);
    --xy-controls-button-background-color: var(--color-panel);
    --xy-controls-button-background-color-hover: color-mix(
      in srgb,
      var(--color-brand-2) 20%,
      var(--color-panel)
    );
    --xy-controls-button-color: var(--color-text);
    --xy-controls-button-color-hover: var(--color-brand-2);
    --xy-controls-button-border-color: var(--color-line);
    --xy-controls-box-shadow: 0 0 14px -4px
      color-mix(in srgb, var(--color-brand-2) 40%, transparent);
    --xy-minimap-background-color: var(--color-panel);
  }
  .flow :global(.svelte-flow__node) {
    font-family: inherit;
    border: 0;
    border-radius: 12px;
    background: transparent;
    box-shadow: none;
    cursor: grab;
    padding: 0;
    transition:
      box-shadow 0.25s var(--ease-smooth),
      border-color 0.25s var(--ease-smooth),
      transform 0.2s var(--ease-smooth);
  }
  .flow :global(.svelte-flow__node.dragging) {
    cursor: grabbing;
  }
  .flow :global(.svelte-flow__node.selected) {
    box-shadow:
      0 0 0 2px var(--color-brand),
      0 0 24px -3px var(--color-brand);
  }
  .flow :global(.svelte-flow__node.selectable:hover) {
    transform: translateY(-1px);
  }
  .flow :global(.svelte-flow__edge.animated path) {
    stroke-dasharray: 4 8;
    animation: data-flow 0.8s linear infinite;
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--color-brand-2) 85%, transparent));
  }
  .flow :global(.svelte-flow__edge:hover .svelte-flow__edge-path) {
    stroke: var(--color-brand);
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--color-brand) 60%, transparent));
  }
  @keyframes data-flow {
    to {
      stroke-dashoffset: -24;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .flow :global(.svelte-flow__edge.animated path) {
      animation: none;
    }
    .flow :global(.svelte-flow__node[style*='node-pulse']) {
      animation: none !important;
    }
  }
</style>
