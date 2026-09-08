<script lang="ts">
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
  let nodes = $derived(lifecycleNodes(activity.tasks, selected));
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
    border: 1px solid #64748b55;
    border-radius: 14px;
    padding: 1rem;
    background: var(--surface, #111827);
    color: var(--text, #e2e8f0);
  }
  .canvas:fullscreen {
    border-radius: 0;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: auto;
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
  p {
    font-size: 0.85rem;
  }
  button {
    border: 1px solid #64748b77;
    padding: 0.65rem;
    border-radius: 8px;
    background: transparent;
    color: inherit;
    cursor: pointer;
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
  }
  .flow {
    height: 440px;
    min-height: 320px;
  }
  .canvas:fullscreen .flow {
    height: calc(100dvh - 240px);
  }
  .guide {
    margin-bottom: 2rem;
  }
  small {
    display: block;
    font-size: 0.75rem;
    opacity: 0.8;
  }
  aside {
    padding: 1rem;
    border-left: 1px solid #64748b55;
    overflow: auto;
  }
  .task {
    width: 100%;
    text-align: left;
    margin-bottom: 0.5rem;
  }
  .task.chosen {
    border-color: #38bdf8;
  }
  .details {
    padding: 1rem 0;
  }
  .milestone {
    padding-bottom: 0.7rem;
    border-bottom: 1px solid #64748b33;
  }
  a {
    color: #7dd3fc;
  }
  @media (max-width: 850px) {
    .workspace {
      grid-template-columns: 1fr;
    }
    aside {
      border-left: 0;
    }
  }
</style>
