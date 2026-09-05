<script lang="ts">
  import type { AgentCheckpoint, TaskMemory } from '$lib/types';
  let { memory, checkpoints }: { memory: TaskMemory | null; checkpoints: AgentCheckpoint[] } =
    $props();
  const sections = $derived(
    memory
      ? [
          ['Decisions', memory.decisions],
          ['Invariants', memory.invariants],
          ['Important files', memory.important_files],
          ['Open questions', memory.open_questions]
        ].filter(([, values]) => values.length)
      : []
  );
</script>

<section class="border-line bg-panel overflow-hidden rounded-xl border xl:col-span-2">
  <header class="border-line flex items-center justify-between border-b p-5">
    <div>
      <small class="text-brand tracking-widest">PERSISTENT CONTEXT</small>
      <h2 class="text-heading font-semibold">AI task memory</h2>
    </div>
    {#if memory}<span class="text-muted font-mono text-xs"
        >v{memory.version} · {memory.current_sha?.slice(0, 8) || 'no revision'}</span
      >{/if}
  </header>
  {#if memory}
    <div class="grid gap-5 p-5 md:grid-cols-2">
      <div>
        <small class="text-muted tracking-wider">GOAL</small>
        <p class="text-heading mt-2 text-sm">{memory.goal}</p>
      </div>
      {#each sections as section (section[0])}
        <div>
          <small class="text-muted tracking-wider">{section[0]}</small>
          <ul class="mt-2 space-y-1 text-sm">
            {#each section[1] as value (value)}<li>• {value}</li>{/each}
          </ul>
        </div>
      {/each}
    </div>
    <div class="border-line border-t p-5">
      <small class="text-muted tracking-wider">RECENT CHECKPOINTS</small>
      <div class="mt-3 grid gap-2 md:grid-cols-2">
        {#each checkpoints.slice(0, 6) as checkpoint (checkpoint.id)}<article
            class="border-line bg-panel-alt rounded-lg border p-3"
          >
            <b class="text-brand text-xs">{checkpoint.role}</b>
            <p class="text-muted mt-1 text-xs">{checkpoint.summary}</p>
          </article>{:else}<p class="text-muted text-xs">
            Checkpoints appear after AI jobs complete.
          </p>{/each}
      </div>
    </div>
  {:else}<p class="text-muted p-5 text-sm">
      Task memory is initialized when this task is loaded by a worker.
    </p>{/if}
</section>
