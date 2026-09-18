<script lang="ts">
  import type { TaskState } from './types';
  let { tasks }: { tasks: TaskState[] } = $props();
  const known = $derived(new Map(tasks.map((task) => [task.id, task])));
  const linked = $derived(tasks.filter((task) => task.dependency_ids?.length));
</script>

<details class="border-t border-line px-4 py-2 text-xs">
  <summary class="cursor-pointer">Task prerequisite history</summary>
  <div class="max-h-44 overflow-auto py-2">
    <p class="text-muted">
      Recorded prerequisites at the playhead. Tasks outside this replay have unknown historical
      status.
    </p>
    {#each linked as task (task.id)}
      <p class="mt-2"><strong>{task.key || task.title}</strong> depends on:</p>
      <ul>
        {#each task.dependency_ids ?? [] as id (id)}
          {@const prerequisite = known.get(id)}
          <li>
            {prerequisite?.key || prerequisite?.title || id} · {prerequisite?.status
              .toLowerCase()
              .replaceAll('_', ' ') || 'outside replay'}
          </li>
        {/each}
      </ul>
    {:else}<p class="mt-2 text-muted">No task prerequisites recorded at this point.</p>{/each}
  </div>
</details>
