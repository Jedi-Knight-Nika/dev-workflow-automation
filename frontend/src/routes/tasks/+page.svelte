<script lang="ts">
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import { API_BASE_URL } from '$lib/api';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import { createLiveRefresh } from '$lib/live-refresh';
  import { listTasks, createTask, type TaskFilters } from '$lib/services/tasks';
  import { listTeams, assignTaskToTeam } from '$lib/services/teams';
  import { listRepositories } from '$lib/services/repositories';
  import { tasksByColumn, priorityLabel, parseEstimate, formatEstimate } from '$lib/task-board';
  import type { Task, Team, Repository } from '$lib/types';

  let tasks = $state<Task[]>([]);
  let teams = $state<Team[]>([]);
  let repositories = $state<Repository[]>([]);
  let loading = $state(true),
    saving = $state(false),
    error = $state('');
  let creating = $state(false),
    view = $state<'board' | 'list'>('board');
  let filters = $state<TaskFilters>({ sort: 'priority', direction: 'asc' });
  let draft = $state({
    title: '',
    description: '',
    priority: 3,
    repository_id: '',
    team_id: '',
    estimate: '',
    project_name: '',
    labels: '',
    due_at: '',
    start_work: false
  });
  const columns = $derived(tasksByColumn(tasks));
  let sequence = 0;
  async function refresh() {
    const request = ++sequence;
    try {
      const result = await listTasks(filters);
      if (request === sequence) {
        tasks = result;
        error = '';
      }
    } catch (cause) {
      if (request === sequence) error = String(cause);
    } finally {
      if (request === sequence) loading = false;
    }
  }
  const live = createLiveRefresh(refresh);
  async function save() {
    if (saving) return;
    saving = true;
    error = '';
    try {
      // Assign before starting so the selected Team owns the native session.
      const task = await createTask({
        title: draft.title.trim(),
        description: draft.description,
        priority: draft.priority,
        repository_id: draft.repository_id || null,
        start_work: draft.start_work && !draft.team_id,
        estimate: parseEstimate(String(draft.estimate ?? '')),
        project_name: draft.project_name || null,
        labels: draft.labels
          .split(',')
          .map((label) => label.trim())
          .filter(Boolean),
        due_at: draft.due_at ? new Date(draft.due_at).toISOString() : null
      });
      if (draft.team_id) await assignTaskToTeam(draft.team_id, task.id, draft.start_work);
      creating = false;
      draft = {
        title: '',
        description: '',
        priority: 3,
        repository_id: '',
        team_id: '',
        estimate: '',
        project_name: '',
        labels: '',
        due_at: '',
        start_work: false
      };
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      saving = false;
    }
  }
  onMount(() => {
    void refresh();
    void Promise.all([listTeams(), listRepositories()])
      .then(([teamRows, repoRows]) => {
        teams = teamRows;
        repositories = repoRows;
      })
      .catch((cause) => {
        error = String(cause);
      });
    const events = new EventSource(API_BASE_URL + '/events/stream');
    events.addEventListener('update', () => live.request());
    const poll = setInterval(() => {
      if (!document.hidden) live.request();
    }, 10000);
    return () => {
      sequence++;
      live.stop();
      events.close();
      clearInterval(poll);
    };
  });
</script>

<PageHeader
  eyebrow="Engineering"
  title="Tasks"
  description="One fixed lifecycle from a requirement to a validated, reviewed merge."
/>
<main class="space-y-5 p-4 sm:p-6 md:p-10">
  {#if error}<ErrorBanner message={error} />{/if}
  <div class="flex flex-wrap items-center gap-3">
    <input
      class="input min-w-48 flex-1"
      aria-label="Search tasks"
      placeholder="Search tasks…"
      bind:value={filters.search}
      oninput={() => live.request()}
    />
    <select
      class="input"
      aria-label="Team filter"
      bind:value={filters.assigned_team_id}
      onchange={() => live.request()}
    >
      <option value="">All Teams</option>{#each teams as team (team.id)}<option value={team.id}
          >{team.name}</option
        >{/each}
    </select>
    <select
      class="input"
      aria-label="Source filter"
      bind:value={filters.provider}
      onchange={() => live.request()}
    >
      <option value="">All sources</option
      >{#each ['trello', 'linear', 'slack', 'github'] as provider (provider)}<option
          value={provider}>{provider}</option
        >{/each}
    </select>
    <select
      class="input"
      aria-label="Sort tasks"
      bind:value={filters.sort}
      onchange={() => live.request()}
    >
      <option value="priority">Priority</option><option value="updated">Updated</option><option
        value="created">Created</option
      ><option value="due">Due date</option>
    </select>
    <button
      class="btn-secondary"
      onclick={() => {
        view = view === 'board' ? 'list' : 'board';
      }}>{view === 'board' ? 'List view' : 'Board view'}</button
    >
    <button
      class="btn-primary"
      onclick={() => {
        creating = !creating;
      }}>{creating ? 'Close form' : 'Create task'}</button
    >
  </div>
  {#if creating}
    <form
      class="border-line bg-panel grid gap-4 rounded-xl border p-5 md:grid-cols-2"
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label class="md:col-span-2"
        >Title<input
          class="input mt-1 w-full"
          required
          maxlength="500"
          bind:value={draft.title}
        /></label
      >
      <label class="md:col-span-2"
        >Requirement<textarea class="input mt-1 min-h-28 w-full" bind:value={draft.description}
        ></textarea></label
      >
      <label
        >Repository<select class="input mt-1 w-full" bind:value={draft.repository_id}
          ><option value="">Route automatically</option
          >{#each repositories.filter((repo) => repo.enabled && !repo.archived_at) as repo (repo.id)}<option
              value={repo.id}>{repo.owner}/{repo.name}</option
            >{/each}</select
        ></label
      >
      <label
        >Team<select class="input mt-1 w-full" bind:value={draft.team_id}
          ><option value="">Route automatically</option
          >{#each teams.filter((team) => team.enabled) as team (team.id)}<option value={team.id}
              >{team.name}</option
            >{/each}</select
        ></label
      >
      <label
        >Priority<select class="input mt-1 w-full" bind:value={draft.priority}
          >{#each [0, 1, 2, 3, 4, 5] as priority (priority)}<option value={priority}
              >{priorityLabel(priority)}</option
            >{/each}</select
        ></label
      >
      <label
        >Story points<input
          class="input mt-1 w-full"
          type="number"
          min="0"
          step="any"
          max="1000000"
          bind:value={draft.estimate}
        /><small class="text-muted"
          >Relative size, not hours. Suggested: 0, 0.5, 1, 2, 3, 5, 8, 13.</small
        ></label
      >
      <label>Project<input class="input mt-1 w-full" bind:value={draft.project_name} /></label>
      <label
        >Labels, comma separated<input class="input mt-1 w-full" bind:value={draft.labels} /></label
      >
      <label
        >Due date<input
          class="input mt-1 w-full"
          type="datetime-local"
          bind:value={draft.due_at}
        /></label
      >
      <label class="flex items-center gap-2"
        ><input type="checkbox" bind:checked={draft.start_work} />Start work after creation</label
      >
      <p class="text-muted text-sm md:col-span-2">
        Starting requires a configured Team, repository, native runtime and spending policy. A
        missing requirement is shown on the ticket; it does not trigger repeated planning.
      </p>
      <button class="btn-primary justify-self-start" disabled={saving}
        >{saving ? 'Saving…' : 'Create task'}</button
      >
    </form>
  {/if}
  {#if loading}<p aria-live="polite">Loading tasks…</p>
  {:else if !tasks.length}<p class="text-muted py-10 text-center">No tasks match these filters.</p>
  {:else if view === 'board'}
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-3 2xl:grid-cols-6">
      {#each columns as column (column.id)}
        <section class="border-line rounded-xl border bg-panel-alt/30 p-3">
          <h2 class="mb-3 flex justify-between font-semibold">
            {column.label}<span class="text-muted">{column.tasks.length}</span>
          </h2>
          <div class="space-y-3">
            {#each column.tasks as task (task.id)}{@render card(task)}{/each}
          </div>
        </section>
      {/each}
    </div>
  {:else}
    <div class="grid gap-3">
      {#each tasks as task (task.id)}{@render card(task)}{/each}
    </div>
  {/if}
  <p class="text-muted text-xs">
    Showing up to 500 matching tickets. Live updates do not call an AI model.
  </p>
</main>
{#snippet card(task: Task)}
  <a
    class="border-line block space-y-2 rounded-lg border bg-panel p-4 hover:border-brand"
    href={resolve('/tasks/[id]', { id: task.id })}
  >
    <p class="text-muted text-xs">
      {task.external_key ?? 'Manual'} · P{task.priority} · {task.team_name ?? 'Unassigned'}
    </p>
    <h3 class="font-medium">{task.title}</h3>
    <p class="font-mono text-xs">{task.status} · {task.stage}</p>
    {#if task.wait_reason !== 'NONE'}<p class="text-warning text-xs">
        {task.wait_reason.replaceAll('_', ' ')}
      </p>{/if}
    <p class="text-muted text-xs">
      {formatEstimate(task.source?.estimate ?? task.estimate)}{task.due_at
        ? ' · Due ' + new Date(task.due_at).toLocaleDateString()
        : ''}
    </p>
  </a>
{/snippet}
