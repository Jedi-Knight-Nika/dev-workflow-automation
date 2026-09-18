<script lang="ts">
  import { onDestroy } from 'svelte';
  import { resolve } from '$app/paths';
  import { api } from '$lib/api';
  import type { Task } from '$lib/types';

  let { task, onChanged }: { task: Task; onChanged: () => Promise<void> } = $props();
  let search = $state(''),
    error = $state(''),
    saving = $state(false),
    searching = $state(false);
  let results = $state<Task[]>([]);
  let controller: AbortController | undefined;
  let disposed = false;
  const dependencies = $derived(task.dependencies ?? []);
  const editable = $derived(['NEW', 'PAUSED'].includes(task.status));
  const blocked = $derived(dependencies.some((dependency) => dependency.status !== 'MERGED'));
  onDestroy(() => {
    disposed = true;
    controller?.abort();
  });

  async function find() {
    controller?.abort();
    const request = new AbortController();
    controller = request;
    searching = true;
    error = '';
    try {
      const found = await api<Task[]>(
        `/tasks?limit=20&search=${encodeURIComponent(search.trim())}`,
        { signal: request.signal }
      );
      if (!request.signal.aborted) results = found.filter((value) => value.id !== task.id);
    } catch (cause) {
      if (!request.signal.aborted) error = String(cause);
    } finally {
      if (!request.signal.aborted) searching = false;
    }
  }

  async function save(ids: string[]) {
    if (saving || !editable) return;
    saving = true;
    error = '';
    let saved = false;
    try {
      await api(`/tasks/${task.id}/dependencies`, {
        method: 'PUT',
        body: JSON.stringify({
          dependency_ids: ids,
          expected_dependency_ids: dependencies.map((value) => value.id)
        })
      });
      saved = true;
      if (!disposed) await onChanged();
    } catch (cause) {
      if (!disposed)
        error = `${saved ? 'Prerequisites saved; refresh the task to see them. ' : ''}${String(cause)}`;
    } finally {
      if (!disposed) saving = false;
    }
  }
</script>

<section
  class="space-y-3 rounded-xl border border-line p-5 xl:col-span-2"
  aria-label="Task prerequisites"
>
  <h2 class="font-semibold">Task prerequisites</h2>
  <p class="text-sm text-muted">
    {blocked
      ? 'Execution waits until every prerequisite is merged.'
      : dependencies.length
        ? 'All prerequisites are merged.'
        : 'This task has no prerequisites.'}
    {#if !editable}
      Pause work to edit prerequisites.{/if}
  </p>
  {#if error}<p role="alert" class="text-sm text-danger">{error}</p>{/if}
  <ul class="space-y-2">
    {#each dependencies as dependency (dependency.id)}
      <li class="flex flex-wrap items-center gap-3 text-sm">
        <a class="text-brand underline" href={resolve('/tasks/[id]', { id: dependency.id })}
          >{dependency.title}</a
        >
        <span class="text-muted">{dependency.status.toLowerCase().replaceAll('_', ' ')}</span>
        {#if editable}<button
            class="btn-secondary"
            disabled={saving}
            onclick={() =>
              save(
                dependencies.filter((value) => value.id !== dependency.id).map((value) => value.id)
              )}>Remove prerequisite</button
          >{/if}
      </li>
    {/each}
  </ul>
  {#if editable}
    <form
      class="flex flex-wrap gap-2"
      onsubmit={(event) => {
        event.preventDefault();
        void find();
      }}
    >
      <input
        class="input"
        aria-label="Find prerequisite task"
        bind:value={search}
        maxlength="200"
        placeholder="Task title or key"
      />
      <button class="btn-secondary" disabled={searching || saving}>Search tasks</button>
    </form>
    {#each results.filter((value) => !dependencies.some((dependency) => dependency.id === value.id)) as result (result.id)}
      <div class="flex items-center justify-between gap-3 text-sm">
        <span>{result.title} · {result.status.toLowerCase()}</span>
        <button
          class="btn-secondary"
          disabled={saving || dependencies.length >= 32}
          onclick={() => save([...dependencies.map((value) => value.id), result.id])}
          >Add prerequisite</button
        >
      </div>
    {/each}
  {/if}
</section>
