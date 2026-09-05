<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import ShowMore from '$lib/components/ShowMore.svelte';
  import { tasksResource } from '$lib/stores/tasks.svelte';
  import type { Task } from '$lib/types';

  onMount(() => {
    tasksResource.load();
  });
</script>

<PageHeader
  eyebrow="WORK INVENTORY"
  title="Tasks"
  description="Durable engineering tasks and their current automation state."
/>
<main class="p-4 sm:p-6 md:p-10">
  <ErrorBanner message={tasksResource.error} />
  <div class="border-line overflow-hidden rounded-xl border">
    {#if tasksResource.loading && tasksResource.data.length === 0}
      <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
      {#each Array(5) as _, index (index)}
        <div
          class="border-line grid gap-2 border-b p-4 last:border-0 md:grid-cols-[90px_1fr_180px]"
        >
          <Skeleton class="h-4 w-8" />
          <div class="flex flex-col gap-2">
            <Skeleton class="h-4 w-40" />
            <Skeleton class="h-3 w-24" />
          </div>
          <Skeleton class="h-4 w-24" />
        </div>
      {/each}
    {:else if tasksResource.data.length === 0}
      <EmptyState message="No tasks yet." />
    {:else}
      <ShowMore items={tasksResource.data}>
        {#snippet children(visibleTasks: Task[])}
          {#each visibleTasks as task, index (task.id)}
            <a
              href={resolve('/tasks/[id]', { id: task.id })}
              class="border-line grid gap-2 border-b p-4 transition-colors last:border-0 hover:bg-panel-alt motion-safe:animate-fade-in-up md:grid-cols-[90px_1fr_180px]"
              style="animation-delay: {Math.min(index, 12) * 25}ms"
            >
              <span class="text-brand font-mono text-xs">P{task.priority}</span>
              <span
                ><strong class="block">{task.title}</strong><small class="text-muted"
                  >{task.external_key || task.id.slice(0, 8)}</small
                ></span
              >
              <span class="font-mono text-xs text-muted">{task.state.replaceAll('_', ' ')}</span>
            </a>
          {/each}
        {/snippet}
      </ShowMore>
    {/if}
  </div>
</main>
