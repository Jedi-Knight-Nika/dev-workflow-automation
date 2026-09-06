<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import { API_URL } from '$lib/api';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import TeamBadge from '$lib/components/TeamBadge.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { listRepositories } from '$lib/services/repositories';
  import { createTask, listTasks, type TaskFilters } from '$lib/services/tasks';
  import { assignTaskToTeam, listTeams, unassignTask } from '$lib/services/teams';
  import { priorityLabel, tasksByColumn } from '$lib/task-board';
  import type { Repository, Task, Team } from '$lib/types';

  let tasks = $state<Task[]>([]),
    selected = $state<Task | null>(null);
  let teams = $state<Team[]>([]),
    assigning = $state(false);
  let repositories = $state<Repository[]>([]);
  let creating = $state(false),
    savingTask = $state(false);
  let draft = $state({
    title: '',
    description: '',
    priority: 3,
    external_key: '',
    repository_id: '',
    team_id: '',
    project_name: '',
    labels: '',
    estimate: '',
    due_at: ''
  });
  let loading = $state(true),
    error = $state(''),
    showAdvanced = $state(false);
  let filters = $state<TaskFilters>({ sort: 'priority', direction: 'asc' });
  let columns = $derived(tasksByColumn(tasks));
  let timer: ReturnType<typeof setTimeout> | undefined;
  let requestId = 0;

  async function refresh() {
    const thisRequest = ++requestId;
    loading = true;
    error = '';
    try {
      const nextTasks = await listTasks(filters);
      if (thisRequest !== requestId) return;
      tasks = nextTasks;
      if (selected) selected = tasks.find((task) => task.id === selected?.id) ?? null;
    } catch (cause) {
      if (thisRequest !== requestId) return;
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      if (thisRequest === requestId) loading = false;
    }
  }
  function queueRefresh() {
    clearTimeout(timer);
    timer = setTimeout(() => void refresh(), 250);
  }
  function resetFilters() {
    filters = { sort: 'priority', direction: 'asc' };
    void refresh();
  }
  async function changeTeam(value: string) {
    if (!selected) return;
    assigning = true;
    error = '';
    try {
      if (value) await assignTaskToTeam(value, selected.id);
      else await unassignTask(selected.id);
      await refresh();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      assigning = false;
    }
  }
  function resetDraft() {
    draft = {
      title: '',
      description: '',
      priority: 3,
      external_key: '',
      repository_id: '',
      team_id: '',
      project_name: '',
      labels: '',
      estimate: '',
      due_at: ''
    };
  }
  async function submitTask() {
    if (!draft.title.trim()) return;
    savingTask = true;
    error = '';
    try {
      const task = await createTask({
        title: draft.title.trim(),
        description: draft.description.trim(),
        priority: draft.priority,
        external_key: draft.external_key.trim() || null,
        repository_id: draft.repository_id || null,
        project_name: draft.project_name.trim() || null,
        labels: [
          ...new Set(
            draft.labels
              .split(',')
              .map((label) => label.trim())
              .filter(Boolean)
          )
        ],
        estimate: draft.estimate === '' ? null : Number(draft.estimate),
        due_at: draft.due_at ? new Date(draft.due_at).toISOString() : null,
        enqueue_planning: false
      });
      if (draft.team_id) await assignTaskToTeam(draft.team_id, task.id);
      creating = false;
      resetDraft();
      await refresh();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      savingTask = false;
    }
  }
  function date(value?: string | null, short = false) {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.valueOf())) return value;
    return short
      ? parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      : parsed.toLocaleString();
  }
  onMount(() => {
    void refresh();
    void Promise.all([listTeams(), listRepositories()])
      .then(([teamResult, repositoryResult]) => {
        teams = teamResult;
        repositories = repositoryResult;
      })
      .catch((cause) => (error = String(cause)));
    const stream = new EventSource(`${API_URL}/api/v1/events/stream`);
    stream.addEventListener('update', queueRefresh);
    return () => {
      clearTimeout(timer);
      stream.close();
    };
  });
</script>

<svelte:window onkeydown={(event) => event.key === 'Escape' && (selected = null)} />
<PageHeader
  eyebrow={t('tasks.eyebrow')}
  title={t('tasks.title')}
  description={t('tasks.description')}
/>

<main class="space-y-5 p-4 sm:p-6 md:p-10">
  <ErrorBanner message={error} />
  <section class="filters" aria-label="Task filters">
    <div class="filter-grid">
      <label
        ><span>Search</span><input
          bind:value={filters.search}
          oninput={queueRefresh}
          placeholder="Title or task ID…"
        /></label
      >
      <label
        ><span>Source</span><select bind:value={filters.provider} onchange={() => void refresh()}
          ><option value="">All sources</option><option value="linear">Linear</option><option
            value="trello">Trello</option
          ><option value="internal">Manual</option><option value="github">GitHub</option></select
        ></label
      >
      <label
        ><span>Assigned team</span><select
          value={filters.unassigned ? '__unassigned__' : filters.assigned_team_id || ''}
          onchange={(event) => {
            const value = event.currentTarget.value;
            filters.unassigned = value === '__unassigned__';
            filters.assigned_team_id = value && value !== '__unassigned__' ? value : '';
            void refresh();
          }}
          ><option value="">All assignments</option><option value="__unassigned__"
            >Unassigned</option
          >{#each teams as team (team.id)}<option value={team.id}>{team.name}</option
            >{/each}</select
        ></label
      >
      <label
        ><span>Priority</span><select
          value={filters.priority?.[0] ?? ''}
          onchange={(event) => {
            const value = event.currentTarget.value;
            filters.priority = value ? [Number(value)] : [];
            void refresh();
          }}
          ><option value="">All priorities</option
          >{#each [0, 1, 2, 3, 4, 5] as priority (priority)}<option value={priority}
              >{priorityLabel(priority)}</option
            >{/each}</select
        ></label
      >
      <label
        ><span>Sort</span><select bind:value={filters.sort} onchange={() => void refresh()}
          ><option value="priority">Priority</option><option value="updated"
            >Recently updated</option
          ><option value="created">Created date</option><option value="due">Due date</option
          ></select
        ></label
      >
      <div class="filter-actions">
        <button onclick={() => (showAdvanced = !showAdvanced)}
          >{showAdvanced ? 'Fewer' : 'More'} filters</button
        ><button onclick={resetFilters}>Clear</button>
      </div>
    </div>
    {#if showAdvanced}
      <div class="advanced">
        {#each [['assignee', 'External assignee'], ['team', 'External team'], ['project', 'Project'], ['label', 'Label'], ['provider_state', 'Source status']] as field (field[0])}
          <label
            ><span>{field[1]}</span><input
              value={String(filters[field[0] as keyof TaskFilters] ?? '')}
              oninput={(event) => {
                filters[field[0] as keyof TaskFilters] = event.currentTarget.value as never;
                queueRefresh();
              }}
              placeholder={`Any ${field[1].toLowerCase()}`}
            /></label
          >
        {/each}
        <label
          ><span>Created after</span><input
            type="date"
            bind:value={filters.created_from}
            onchange={() => void refresh()}
          /></label
        >
      </div>
    {/if}
  </section>
  <div class="toolbar">
    <span>{tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}</span>
    <div>
      <button disabled={loading} onclick={() => void refresh()}
        >{loading ? 'Refreshing…' : 'Refresh'}</button
      ><button class="create-button" onclick={() => (creating = true)}>+ Create manual task</button>
    </div>
  </div>

  {#if loading && tasks.length === 0}
    <div class="loading-grid">
      <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
      {#each Array(6) as _, index (index)}
        <Skeleton class="h-72 rounded-xl" />
      {/each}
    </div>
  {:else if tasks.length === 0}
    <div class="empty"><EmptyState message={t('tasks.empty')} /></div>
  {:else}
    <section class="board" aria-label="Task board">
      {#each columns as column (column.id)}
        <div class="column">
          <header>
            <span
              class:attention={column.id === 'attention'}
              class:done={column.id === 'done'}
              class="dot"
            ></span><strong>{column.label}</strong><span class="count">{column.tasks.length}</span>
          </header>
          <div class="cards">
            {#each column.tasks as task (task.id)}
              <button class="task-card" onclick={() => (selected = task)}>
                <div class="card-top">
                  <span class="source-id"
                    >{task.source?.identifier || task.external_key || task.id.slice(0, 8)}</span
                  ><span>P{task.priority}</span>
                </div>
                <strong>{task.title}</strong>
                {#if task.description}<p>{task.description}</p>{/if}
                <div class="metadata">
                  <span class="chip brand">{task.source?.provider || 'manual'}</span>
                  <TeamBadge id={task.team_id} name={task.team_name} compact />
                  {#if task.source?.state_name}<span class="chip">{task.source.state_name}</span
                    >{/if}
                  {#if task.source?.assignee_name}<span
                      class="avatar"
                      title={task.source.assignee_name}
                      >{task.source.assignee_name.slice(0, 1)}</span
                    >{/if}
                  {#if task.due_at || task.source?.due_date}<span class="due"
                      >Due {date(task.due_at || task.source?.due_date, true)}</span
                    >{/if}
                </div>
                {#if task.source?.labels.length || task.labels?.length}<div class="labels">
                    {#each (task.source?.labels || task.labels || []).slice(0, 3) as label (label)}<span
                        >{label}</span
                      >{/each}
                  </div>{/if}
              </button>
            {/each}
            {#if column.tasks.length === 0}<div class="no-cards">No tasks</div>{/if}
          </div>
        </div>
      {/each}
    </section>
  {/if}
</main>

{#if creating}
  <button class="backdrop" aria-label="Close task creation" onclick={() => (creating = false)}
  ></button>
  <div class="create-modal" role="dialog" aria-modal="true" aria-labelledby="create-task-title">
    <header>
      <div>
        <span class="source-id">Internal task</span>
        <h2 id="create-task-title">Create manual task</h2>
      </div>
      <button class="close" aria-label="Close" onclick={() => (creating = false)}>×</button>
    </header>
    <form
      onsubmit={(event) => {
        event.preventDefault();
        void submitTask();
      }}
    >
      <div class="form-grid">
        <label class="wide"
          ><span>Title *</span><input
            bind:value={draft.title}
            required
            maxlength="500"
            placeholder="What needs to be done?"
          /></label
        >
        <label class="wide"
          ><span>Description</span><textarea
            bind:value={draft.description}
            rows="6"
            placeholder="Requirements, context, and definition of done…"
          ></textarea></label
        >
        <label
          ><span>Priority</span><select bind:value={draft.priority}
            >{#each [0, 1, 2, 3, 4, 5] as priority (priority)}<option value={priority}
                >{priorityLabel(priority)}</option
              >{/each}</select
          ></label
        >
        <label
          ><span>AI team</span><select bind:value={draft.team_id}
            ><option value="">Unassigned</option
            >{#each teams.filter((team) => team.enabled) as team (team.id)}<option value={team.id}
                >{team.name}</option
              >{/each}</select
          ></label
        >
        <label
          ><span>Repository</span><select bind:value={draft.repository_id}
            ><option value="">No repository</option
            >{#each repositories.filter((repository) => repository.enabled) as repository (repository.id)}<option
                value={repository.id}>{repository.owner}/{repository.name}</option
              >{/each}</select
          ></label
        >
        <label
          ><span>Project</span><input
            bind:value={draft.project_name}
            maxlength="255"
            placeholder="Optional project"
          /></label
        >
        <label
          ><span>Reference key</span><input
            bind:value={draft.external_key}
            maxlength="100"
            placeholder="e.g. MAN-42"
          /></label
        >
        <label
          ><span>Estimate</span><input
            bind:value={draft.estimate}
            type="number"
            min="0"
            max="1000000"
            step="0.5"
            placeholder="Points or hours"
          /></label
        >
        <label><span>Due date</span><input bind:value={draft.due_at} type="datetime-local" /></label
        >
        <label class="wide"
          ><span>Labels</span><input
            bind:value={draft.labels}
            placeholder="backend, billing, urgent"
          /><small>Separate labels with commas.</small></label
        >
      </div>
      <footer>
        <button type="button" class="secondary" onclick={() => (creating = false)}>Cancel</button
        ><button type="submit" class="primary" disabled={savingTask || !draft.title.trim()}
          >{savingTask ? 'Creating…' : draft.team_id ? 'Create and assign' : 'Create task'}</button
        >
      </footer>
    </form>
  </div>
{/if}

{#if selected}
  <button class="backdrop" aria-label="Close task details" onclick={() => (selected = null)}
  ></button>
  <aside class="drawer" aria-label="Task details">
    <header>
      <div>
        <span class="source-id"
          >{selected.source?.identifier || selected.external_key || selected.id}</span
        >
        <h2>{selected.title}</h2>
      </div>
      <button class="close" aria-label="Close" onclick={() => (selected = null)}>×</button>
    </header>
    <div class="drawer-body">
      <div class="state">
        <span>{selected.state.replaceAll('_', ' ')}</span><span
          >{priorityLabel(selected.priority)}</span
        >
      </div>
      <section class="assignment">
        <h3>AI team assignee</h3>
        <div class="assignment-control">
          <TeamBadge id={selected.team_id} name={selected.team_name} />
          <select
            disabled={assigning}
            value={selected.team_id || ''}
            onchange={(event) => void changeTeam(event.currentTarget.value)}
          >
            <option value="">Unassigned</option>
            {#each teams as team (team.id)}<option value={team.id}>{team.name}</option>{/each}
          </select>
        </div>
        <p>
          {selected.team_id
            ? 'Changing this moves the task into another team queue.'
            : 'Assign a team to start this task.'}
        </p>
      </section>
      <section>
        <h3>Description</h3>
        <p class="description">{selected.description || 'No description provided.'}</p>
      </section>
      <section>
        <h3>Details</h3>
        <dl>
          <div>
            <dt>Source</dt>
            <dd>{selected.source?.provider || 'Internal'}</dd>
          </div>
          <div>
            <dt>Source status</dt>
            <dd>{selected.source?.state_name || '—'}</dd>
          </div>
          <div>
            <dt>Assignee</dt>
            <dd>{selected.source?.assignee_name || selected.source?.assignee_email || '—'}</dd>
          </div>
          <div>
            <dt>Creator</dt>
            <dd>{selected.source?.creator_name || '—'}</dd>
          </div>
          <div>
            <dt>External team</dt>
            <dd>{selected.source?.team_name || '—'}</dd>
          </div>
          <div>
            <dt>Project</dt>
            <dd>{selected.source?.project_name || selected.project_name || '—'}</dd>
          </div>
          <div>
            <dt>Repository</dt>
            <dd>{selected.repository_name || '—'}</dd>
          </div>
          <div>
            <dt>Estimate</dt>
            <dd>{selected.source?.estimate ?? selected.estimate ?? '—'}</dd>
          </div>
          <div>
            <dt>Due</dt>
            <dd>{date(selected.due_at || selected.source?.due_date)}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{date(selected.source?.provider_created_at || selected.created_at)}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{date(selected.source?.provider_updated_at || selected.updated_at)}</dd>
          </div>
          <div>
            <dt>Completed</dt>
            <dd>{date(selected.completed_at)}</dd>
          </div>
        </dl>
      </section>
      {#if selected.source?.labels.length || selected.labels?.length}<section>
          <h3>Labels</h3>
          <div class="labels">
            {#each selected.source?.labels || selected.labels || [] as label (label)}<span
                >{label}</span
              >{/each}
          </div>
        </section>{/if}
      <details>
        <summary>Raw provider data</summary>
        <pre>{JSON.stringify(selected.source?.raw_payload ?? {}, null, 2)}</pre>
      </details>
    </div>
    <footer>
      {#if selected.source?.url}
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
        <a class="secondary" href={selected.source.url} target="_blank" rel="noreferrer"
          >Open in {selected.source.provider}</a
        >{/if}<a class="primary" href={resolve('/tasks/[id]', { id: selected.id })}
        >Open full task</a
      >
    </footer>
  </aside>
{/if}

<style>
  .filters {
    border: 1px solid var(--color-line);
    border-radius: 0.8rem;
    background: var(--color-panel);
    padding: 0.75rem;
    box-shadow: 0 1px 2px rgb(0 0 0/0.04);
  }
  .filter-grid {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: minmax(220px, 1fr) repeat(3, 160px) auto;
  }
  .filters label {
    display: grid;
    gap: 0.3rem;
    color: var(--color-muted);
    font-size: 0.7rem;
  }
  .filters label span {
    font-weight: 650;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .filters input,
  .filters select {
    min-height: 2.4rem;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    background: var(--color-bg);
    padding: 0.45rem 0.65rem;
    color: var(--color-text);
    font-size: 0.84rem;
    outline: none;
  }
  .filters input:focus,
  .filters select:focus {
    border-color: var(--color-brand);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand) 18%, transparent);
  }
  .filter-actions {
    display: flex;
    align-items: end;
    gap: 0.4rem;
  }
  .filter-actions button {
    min-height: 2.4rem;
    white-space: nowrap;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    padding: 0 0.65rem;
    color: var(--color-muted);
    font-size: 0.78rem;
  }
  .filter-actions button:hover {
    background: var(--color-panel-alt);
    color: var(--color-text);
  }
  .advanced {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 0.5rem;
    margin-top: 0.75rem;
    border-top: 1px solid var(--color-line);
    padding-top: 0.75rem;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--color-muted);
    font-size: 0.8rem;
  }
  .toolbar button {
    color: var(--color-brand);
  }
  .toolbar > div {
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }
  .toolbar .create-button {
    border-radius: 0.55rem;
    background: var(--color-brand);
    padding: 0.6rem 0.85rem;
    color: white;
    font-weight: 700;
  }
  .toolbar button:disabled {
    opacity: 0.5;
  }
  .loading-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 0.75rem;
  }
  .empty {
    border: 1px solid var(--color-line);
    border-radius: 0.8rem;
  }
  .board {
    display: grid;
    grid-auto-columns: minmax(260px, 1fr);
    grid-auto-flow: column;
    gap: 0.75rem;
    overflow-x: auto;
    padding-bottom: 0.75rem;
    scroll-snap-type: x proximity;
  }
  .column {
    min-height: 30rem;
    border: 1px solid var(--color-line);
    border-radius: 0.8rem;
    background: color-mix(in srgb, var(--color-panel-alt) 76%, transparent);
    scroll-snap-align: start;
  }
  .column > header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-height: 3rem;
    border-bottom: 1px solid var(--color-line);
    padding: 0 0.8rem;
    font-size: 0.8rem;
  }
  .dot {
    width: 0.55rem;
    height: 0.55rem;
    border: 2px solid var(--color-muted);
    border-radius: 999px;
  }
  .dot.done {
    border-color: #22a06b;
    background: #22a06b;
  }
  .dot.attention {
    border-color: #e5484d;
    background: #e5484d;
  }
  .count {
    margin-left: auto;
    border-radius: 999px;
    background: var(--color-bg);
    padding: 0.12rem 0.45rem;
    color: var(--color-muted);
    font:
      0.7rem ui-monospace,
      monospace;
  }
  .cards {
    display: grid;
    align-content: start;
    gap: 0.55rem;
    padding: 0.55rem;
  }
  .task-card {
    display: grid;
    gap: 0.55rem;
    width: 100%;
    border: 1px solid var(--color-line);
    border-radius: 0.65rem;
    background: var(--color-panel);
    padding: 0.75rem;
    text-align: left;
    box-shadow: 0 1px 2px rgb(0 0 0/0.04);
    transition: 120ms;
  }
  .task-card:hover {
    border-color: color-mix(in srgb, var(--color-brand) 48%, var(--color-line));
    box-shadow: 0 5px 14px rgb(0 0 0/0.08);
    transform: translateY(-1px);
  }
  .task-card > strong {
    font-size: 0.88rem;
    line-height: 1.35;
  }
  .task-card p {
    display: -webkit-box;
    overflow: hidden;
    color: var(--color-muted);
    font-size: 0.76rem;
    line-height: 1.45;
    line-clamp: 2;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .card-top {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    color: var(--color-muted);
    font:
      0.68rem ui-monospace,
      monospace;
  }
  .source-id {
    color: var(--color-muted);
    font:
      0.68rem ui-monospace,
      monospace;
    text-transform: uppercase;
  }
  .metadata,
  .labels {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
  }
  .chip,
  .labels span {
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.14rem 0.4rem;
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .chip.brand {
    color: var(--color-brand);
    text-transform: capitalize;
  }
  .avatar {
    display: grid;
    width: 1.35rem;
    height: 1.35rem;
    place-items: center;
    border-radius: 999px;
    background: var(--color-brand);
    color: white;
    font-size: 0.65rem;
    font-weight: 700;
  }
  .due {
    margin-left: auto;
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .no-cards {
    padding: 2rem 0.5rem;
    text-align: center;
    color: var(--color-muted);
    font-size: 0.75rem;
  }
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    width: 100%;
    background: rgb(0 0 0/0.35);
    backdrop-filter: blur(2px);
  }
  .drawer {
    position: fixed;
    inset: 0 0 0 auto;
    z-index: 50;
    display: grid;
    width: min(580px, 100%);
    grid-template-rows: auto 1fr auto;
    border-left: 1px solid var(--color-line);
    background: var(--color-bg);
    box-shadow: -20px 0 60px rgb(0 0 0/0.18);
    animation: slide-in 180ms ease-out;
  }
  .create-modal {
    position: fixed;
    inset: 50% auto auto 50%;
    z-index: 50;
    width: min(720px, calc(100% - 2rem));
    max-height: calc(100vh - 2rem);
    overflow: auto;
    transform: translate(-50%, -50%);
    border: 1px solid var(--color-line);
    border-radius: 0.9rem;
    background: var(--color-bg);
    box-shadow: 0 24px 80px rgb(0 0 0/0.3);
  }
  .create-modal > header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    border-bottom: 1px solid var(--color-line);
    padding: 1.2rem 1.3rem;
  }
  .create-modal h2 {
    margin-top: 0.25rem;
    font-size: 1.2rem;
    font-weight: 750;
  }
  .create-modal form {
    padding: 1.2rem 1.3rem 0;
  }
  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.85rem;
  }
  .form-grid label {
    display: grid;
    gap: 0.35rem;
    color: var(--color-muted);
    font-size: 0.72rem;
    font-weight: 650;
  }
  .form-grid .wide {
    grid-column: 1 / -1;
  }
  .form-grid input,
  .form-grid select,
  .form-grid textarea {
    width: 100%;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    background: var(--color-panel);
    padding: 0.65rem 0.7rem;
    color: var(--color-text);
    font-size: 0.84rem;
    font-weight: 400;
    outline: none;
  }
  .form-grid textarea {
    resize: vertical;
  }
  .form-grid input:focus,
  .form-grid select:focus,
  .form-grid textarea:focus {
    border-color: var(--color-brand);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand) 18%, transparent);
  }
  .form-grid small {
    font-weight: 400;
  }
  .create-modal footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 1.2rem;
    border-top: 1px solid var(--color-line);
    padding: 1rem 0;
  }
  .create-modal button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
  .drawer > header {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--color-line);
    padding: 1.25rem;
  }
  .drawer h2 {
    margin-top: 0.35rem;
    font-size: 1.25rem;
    font-weight: 720;
    line-height: 1.3;
  }
  .close {
    color: var(--color-muted);
    font-size: 1.75rem;
    line-height: 1;
  }
  .drawer-body {
    overflow-y: auto;
    padding: 1.25rem;
  }
  .drawer-body section {
    margin-top: 1.5rem;
  }
  .drawer-body h3 {
    margin-bottom: 0.7rem;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .state {
    display: flex;
    justify-content: space-between;
    border-radius: 0.55rem;
    background: var(--color-panel-alt);
    padding: 0.65rem 0.8rem;
    color: var(--color-muted);
    font:
      0.72rem ui-monospace,
      monospace;
  }
  .description {
    white-space: pre-wrap;
    color: var(--color-muted);
    font-size: 0.88rem;
    line-height: 1.65;
  }
  .assignment {
    border: 1px solid var(--color-line);
    border-radius: 0.7rem;
    background: var(--color-panel);
    padding: 0.8rem;
  }
  .assignment-control {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }
  .assignment-control select {
    min-width: 11rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-bg);
    padding: 0.5rem;
    color: var(--color-text);
    font-size: 0.75rem;
  }
  .assignment > p {
    margin-top: 0.55rem;
    color: var(--color-muted);
    font-size: 0.7rem;
  }
  dl {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border: 1px solid var(--color-line);
    border-radius: 0.7rem;
    overflow: hidden;
  }
  dl div {
    display: grid;
    gap: 0.2rem;
    border-bottom: 1px solid var(--color-line);
    padding: 0.65rem 0.75rem;
  }
  dl div:nth-child(odd) {
    border-right: 1px solid var(--color-line);
  }
  dt {
    color: var(--color-muted);
    font-size: 0.66rem;
    text-transform: uppercase;
  }
  dd {
    overflow-wrap: anywhere;
    font-size: 0.8rem;
  }
  details {
    margin-top: 1.5rem;
    color: var(--color-muted);
    font-size: 0.75rem;
  }
  pre {
    max-height: 20rem;
    overflow: auto;
    margin-top: 0.6rem;
    border-radius: 0.55rem;
    background: var(--color-panel-alt);
    padding: 0.8rem;
    font-size: 0.67rem;
  }
  .drawer > footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    border-top: 1px solid var(--color-line);
    padding: 1rem 1.25rem;
  }
  .primary,
  .secondary {
    border-radius: 0.55rem;
    padding: 0.65rem 0.9rem;
    font-size: 0.8rem;
    font-weight: 650;
  }
  .primary {
    background: var(--color-brand);
    color: white;
  }
  .secondary {
    border: 1px solid var(--color-line);
  }
  @keyframes slide-in {
    from {
      transform: translateX(2rem);
      opacity: 0;
    }
  }
  @media (max-width: 1024px) {
    .filter-grid {
      grid-template-columns: 1fr 1fr;
    }
    .advanced {
      grid-template-columns: repeat(3, 1fr);
    }
    .loading-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }
  @media (max-width: 640px) {
    .filter-grid,
    .advanced {
      grid-template-columns: 1fr;
    }
    .loading-grid {
      grid-template-columns: 1fr 1fr;
    }
    dl {
      grid-template-columns: 1fr;
    }
    dl div:nth-child(odd) {
      border-right: 0;
    }
  }
</style>
