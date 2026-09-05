<script lang="ts">
  import { env } from '$env/dynamic/public';
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type {
    DashboardActivity,
    Integration,
    Repository,
    WebhookHealth,
    WorkerNode
  } from '$lib/types';

  type Task = {
    id: string;
    external_key: string | null;
    title: string;
    description: string;
    priority: number;
    state: string;
    created_at: string;
  };

  const API = env.PUBLIC_API_URL || '';
  let tasks: Task[] = [];
  let repositories: Repository[] = [];
  let workers: WorkerNode[] = [];
  let activity: DashboardActivity = { active_job: null, queued_jobs: [] };
  let integrations: Integration[] = [];
  let webhookHealth: WebhookHealth[] = [];
  let repositoryId = '';
  let title = '';
  let description = '';
  let loading = true;
  let error = '';

  async function loadTasks() {
    try {
      const response = await fetch(`${API}/api/v1/tasks`);
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      tasks = await response.json();
      error = '';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load tasks';
    } finally {
      loading = false;
    }
  }

  async function loadOperations() {
    [activity, integrations, webhookHealth] = await Promise.all([
      api<DashboardActivity>('/activity'),
      api<Integration[]>('/integrations'),
      api<WebhookHealth[]>('/webhook-health')
    ]);
  }

  async function loadRepositories() {
    const response = await fetch(`${API}/api/v1/repositories`);
    if (response.ok) repositories = await response.json();
  }

  async function loadWorkers() {
    const response = await fetch(`${API}/api/v1/workers`);
    if (response.ok) workers = await response.json();
  }

  async function createTask(event: SubmitEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    const response = await fetch(`${API}/api/v1/tasks`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        title,
        description,
        priority: 3,
        repository_id: repositoryId || null,
        enqueue_planning: true
      })
    });
    if (!response.ok) {
      error = `Create failed: ${response.status}`;
      return;
    }
    title = '';
    description = '';
    repositoryId = '';
    await loadTasks();
  }

  function dashboardGroups(): Array<{ label: string; tasks: Task[] }> {
    const queuedTasks = activity.queued_jobs
      .map((job) => tasks.find((task) => task.id === job.task_id))
      .filter((task): task is Task => task !== undefined);
    return [
      { label: 'PRIORITIZED QUEUE', tasks: queuedTasks },
      {
        label: 'WAITING / READY',
        tasks: tasks.filter((task) => ['WAITING_GITHUB', 'READY_TO_MERGE'].includes(task.state))
      },
      {
        label: 'RECENTLY COMPLETED',
        tasks: tasks.filter((task) => task.state === 'MERGED').slice(0, 6)
      }
    ];
  }

  onMount(() => {
    loadTasks();
    loadRepositories();
    loadWorkers();
    loadOperations();
    const events = new EventSource(`${API}/api/v1/events/stream`);
    events.addEventListener('update', () => {
      loadTasks();
      loadOperations();
      loadRepositories();
    });
    events.onerror = () => {
      error = 'Live connection interrupted; retrying…';
    };
    return () => events.close();
  });
</script>

<svelte:head><title>Engineering Worker</title></svelte:head>

<header class="border-line flex h-[72px] items-center justify-between border-b bg-[#0d110f] px-6">
  <div class="mx-auto flex w-full max-w-[1180px] items-center justify-between">
    <div class="flex items-center gap-3">
      <span
        class="border-accent text-accent grid size-[38px] place-items-center border text-xs font-extrabold"
        >AW</span
      >
      <div class="flex flex-col">
        <strong>Engineering Worker</strong>
        <small class="text-[11px] tracking-[.12em] text-[#758078] uppercase">Control center</small>
      </div>
    </div>
    <div class="text-muted flex items-center gap-2 text-xs">
      <i
        class="size-[7px] rounded-full {workers.some((worker) => worker.online)
          ? 'bg-accent shadow-[0_0_12px_#56f28d]'
          : 'bg-[#ff897d]'}"
      ></i>
      {workers.some((worker) => worker.online)
        ? `${workers.filter((worker) => worker.online).length} worker online`
        : 'No worker heartbeat'}
    </div>
  </div>
</header>

<main class="mx-auto max-w-[1180px] px-6 py-10 md:py-16">
  <section class="grid items-start gap-8 lg:grid-cols-[1fr_460px] lg:gap-20">
    <div>
      <p class="text-accent mb-3.5 font-mono text-[11px] font-bold tracking-[.18em]">
        AUTOMATION QUEUE
      </p>
      <h1
        class="max-w-[600px] text-[42px] leading-[1.02] font-bold tracking-[-.045em] md:text-[58px]"
      >
        Ship work, not busywork.
      </h1>
      <p class="text-muted max-w-[550px] text-[17px] leading-[1.65]">
        Plan, execute, review, and monitor engineering tasks from one durable workflow.
      </p>
    </div>
    <form class="border-line bg-panel p-6 shadow-[12px_12px_0_#070908]" onsubmit={createTask}>
      <label class="mb-3 block text-xs font-bold" for="task-title">New engineering task</label>
      <input
        class="border-line mb-2.5 w-full border bg-[#090c0a] p-[13px] text-white outline-none focus:border-accent"
        id="task-title"
        bind:value={title}
        placeholder="What needs to change?"
        maxlength="500"
      />
      <textarea
        class="border-line mb-2.5 h-[90px] w-full resize-y border bg-[#090c0a] p-[13px] text-white outline-none focus:border-accent"
        bind:value={description}
        placeholder="Requirements, constraints, acceptance criteria…"
      ></textarea>
      <select
        class="border-line mb-2.5 w-full border bg-[#090c0a] p-[13px] text-white outline-none focus:border-accent"
        bind:value={repositoryId}
        aria-label="Repository"
      >
        <option value="">No repository selected</option>
        {#each repositories as repository (repository.id)}
          <option value={repository.id}>{repository.owner}/{repository.name}</option>
        {/each}
      </select>
      <button
        class="bg-accent flex w-full cursor-pointer justify-between p-[13px] font-extrabold text-[#07100a]"
        type="submit">Queue task <span>→</span></button
      >
    </form>
  </section>

  <section class="border-line mb-16 border p-5">
    <div class="flex items-center justify-between gap-4">
      <div>
        <p class="text-accent mb-2 font-mono text-[11px] font-bold tracking-[.18em]">
          WORKER FLEET
        </p>
        <h2 class="m-0 text-xl font-bold">Execution capacity</h2>
      </div>
      <button
        class="border-line text-muted cursor-pointer border bg-transparent px-3 py-2 text-xs"
        onclick={loadWorkers}>Refresh</button
      >
    </div>
    {#if workers.length === 0}
      <p class="text-muted mt-4 text-sm">No worker has registered yet.</p>
    {:else}
      <div class="mt-4 grid gap-2">
        {#each workers as worker (worker.id)}
          <div
            class="border-line flex flex-wrap items-center justify-between gap-3 border p-3 text-sm"
          >
            <div>
              <strong>{worker.hostname}</strong><span class="text-muted ml-2 font-mono text-xs"
                >PID {worker.process_id}</span
              >
            </div>
            <div class="flex items-center gap-3">
              <span class="text-muted text-xs">{worker.capabilities.join(' · ')}</span>
              <span
                class="font-mono text-[10px] font-bold {worker.online
                  ? 'text-accent'
                  : 'text-[#ff897d]'}">{worker.online ? 'ONLINE' : 'OFFLINE'}</span
              >
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <section class="border-line my-16 grid grid-cols-2 border lg:grid-cols-4">
    {#each [[tasks.length, 'Total tasks'], [tasks.filter( (t) => ['PLANNING', 'IMPLEMENTING', 'INTERNAL_REVIEW'].includes(t.state) ).length, 'Active'], [tasks.filter((t) => t.state === 'WAITING_GITHUB').length, 'Waiting'], [tasks.filter( (t) => ['CONTEXT_PENDING', 'NEEDS_HUMAN'].includes(t.state) ).length, 'Needs attention']] as metric, index (`${metric[1]}`)}
      <div
        class:border-r={index % 2 === 0}
        class:border-b={index < 2}
        class="border-line flex flex-col p-6 lg:border-r lg:border-b-0 last:lg:border-r-0"
      >
        <b class="font-mono text-[32px] font-medium">{metric[0]}</b>
        <span class="mt-1 text-xs text-[#758078]">{metric[1]}</span>
      </div>
    {/each}
  </section>

  <section class="mb-16 grid gap-4 lg:grid-cols-3">
    <article class="border-line bg-panel border p-5">
      <p class="text-accent font-mono text-[10px] tracking-widest">CURRENTLY WORKING</p>
      {#if activity.active_job}
        {@const activeTask = tasks.find((task) => task.id === activity.active_job?.task_id)}
        <a
          class="mt-3 block hover:text-accent"
          href={resolve('/tasks/[id]', { id: activity.active_job.task_id })}
        >
          <strong
            >{activeTask?.external_key ||
              activeTask?.title ||
              activity.active_job.task_id.slice(0, 8)}</strong
          >
          <span class="text-muted mt-1 block text-xs"
            >{activity.active_job.role} · {activity.active_job.action.replaceAll('_', ' ')}</span
          >
        </a>
      {:else}<p class="text-muted mt-3 text-sm">Execution lane is idle.</p>{/if}
    </article>
    <article class="border-line bg-panel border p-5">
      <p class="text-accent font-mono text-[10px] tracking-widest">INTEGRATION HEALTH</p>
      {#each integrations.filter( (item) => ['github', 'linear'].includes(item.provider_name) ) as integration (integration.id)}
        {@const hook = webhookHealth.find((item) => item.provider === integration.provider_name)}
        <div class="border-line mt-3 flex justify-between border-b pb-2 text-xs">
          <span>{integration.provider_name.toUpperCase()}</span>
          <span
            class={integration.status === 'CONNECTED' && !hook?.failed
              ? 'text-accent'
              : 'text-[#ff897d]'}
            >{integration.status} · {hook?.pending || 0} pending · {hook?.failed || 0} failed</span
          >
        </div>
      {:else}<p class="text-muted mt-3 text-sm">No integrations configured.</p>{/each}
    </article>
    <article class="border-line bg-panel border p-5">
      <p class="text-accent font-mono text-[10px] tracking-widest">INDEX HEALTH</p>
      <p class="mt-3 text-2xl font-mono">
        {repositories.filter((repository) => repository.index_status === 'READY')
          .length}/{repositories.length}
      </p>
      <p class="text-muted text-xs">repositories ready for retrieval</p>
      {#if repositories.some((repository) => repository.index_status === 'FAILED')}
        <p class="mt-2 text-xs text-red-300">
          {repositories.filter((repository) => repository.index_status === 'FAILED').length} index failures
          need attention
        </p>
      {/if}
    </article>
  </section>

  <section class="mb-16 grid gap-5 lg:grid-cols-3">
    {#each dashboardGroups() as group (group.label)}
      <article class="border-line border p-5">
        <p class="text-accent mb-3 font-mono text-[10px] tracking-widest">{group.label}</p>
        {#each group.tasks as task, index (`${group.label}-${task.id}-${index}`)}
          <a
            class="border-line flex justify-between gap-3 border-b py-2 text-xs hover:text-accent"
            href={resolve('/tasks/[id]', { id: task.id })}
          >
            <span>P{task.priority} · {task.external_key || task.title}</span><span
              >{task.state.replaceAll('_', ' ')}</span
            >
          </a>
        {:else}<p class="text-muted text-sm">None.</p>{/each}
      </article>
    {/each}
  </section>

  <section>
    <div class="flex items-end justify-between">
      <div>
        <p class="text-accent mb-3.5 font-mono text-[11px] font-bold tracking-[.18em]">
          CURRENT WORK
        </p>
        <h2 class="m-0 text-[27px] font-bold">Task queue</h2>
      </div>
      <button
        class="border-line text-muted cursor-pointer border bg-transparent px-3 py-2 text-xs"
        onclick={loadTasks}>Refresh</button
      >
    </div>
    {#if error}<p class="mt-5 bg-[#291511] p-2.5 text-[#ff897d]">{error}</p>{/if}
    {#if loading}
      <p
        class="border-line mt-5 flex min-h-[150px] items-center justify-center border border-dashed text-[#6f7971]"
      >
        Loading durable state…
      </p>
    {:else if tasks.length === 0}
      <div
        class="border-line mt-5 flex min-h-[150px] flex-col items-center justify-center gap-2 border border-dashed text-[#6f7971]"
      >
        <strong class="text-[#aeb8b0]">The lane is clear.</strong>
        <span>Queue the first task above to validate the worker pipeline.</span>
      </div>
    {:else}
      <div class="border-line mt-5 border-t">
        {#each tasks as task (task.id)}
          <article
            class="border-line grid grid-cols-[40px_1fr] items-center gap-5 border-b px-1 py-5 md:grid-cols-[55px_1fr_auto]"
          >
            <div class="text-accent font-mono text-xs font-bold">P{task.priority}</div>
            <div>
              <small class="font-mono text-[11px] text-[#657068]"
                >{task.external_key || task.id.slice(0, 8)}</small
              >
              <h3 class="my-1 text-base font-semibold">{task.title}</h3>
              <p class="m-0 text-[13px] text-[#778178]">
                {task.description || 'No additional context provided.'}
              </p>
            </div>
            <div
              class="border-line col-start-2 justify-self-start border px-2 py-1.5 font-mono text-[10px] font-bold tracking-[.08em] text-[#a4afa7] md:col-start-auto {task.state ===
              'NEEDS_HUMAN'
                ? 'border-[#715125] text-[#ffbd66]'
                : ''}"
            >
              {task.state.replaceAll('_', ' ')}
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </section>
</main>
