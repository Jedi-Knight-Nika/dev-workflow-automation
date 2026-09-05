<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/PageHeader.svelte';
  import { api } from '$lib/api';
  import type { Task } from '$lib/types';
  let tasks: Task[] = [];
  let error = '';
  onMount(async () => {
    try {
      tasks = await api<Task[]>('/tasks');
    } catch (cause) {
      error = String(cause);
    }
  });
</script>

<PageHeader
  eyebrow="WORK INVENTORY"
  title="Tasks"
  description="Durable engineering tasks and their current automation state."
/>
<main class="p-6 md:p-10">
  {#if error}<p class="bg-red-950 p-3 text-red-300">{error}</p>{/if}
  <div class="border-line overflow-hidden border">
    {#each tasks as task (task.id)}
      <a
        href={resolve('/tasks/[id]', { id: task.id })}
        class="border-line grid gap-2 border-b p-4 last:border-0 hover:bg-[#111613] md:grid-cols-[90px_1fr_180px]"
      >
        <span class="text-accent font-mono text-xs">P{task.priority}</span>
        <span
          ><strong class="block">{task.title}</strong><small class="text-muted"
            >{task.external_key || task.id.slice(0, 8)}</small
          ></span
        >
        <span class="font-mono text-xs text-[#a4afa7]">{task.state.replaceAll('_', ' ')}</span>
      </a>
    {:else}<p class="text-muted p-8 text-center">No tasks yet.</p>{/each}
  </div>
</main>
