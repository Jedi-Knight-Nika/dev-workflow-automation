<script lang="ts">
  import CoordinatorPanel from '$lib/components/coordination/CoordinatorPanel.svelte';
  let coordinationMode = $state<'off' | 'shadow' | 'active'>('off');
  import { page } from '$app/state';
  import { afterNavigate } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import TaskResourceBreakdown from '$lib/components/observability/TaskResourceBreakdown.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TaskControls from '$lib/components/task-detail/TaskControls.svelte';
  import TaskConversation from '$lib/components/task-detail/TaskConversation.svelte';
  import TaskDescription from '$lib/components/task-detail/TaskDescription.svelte';
  import TaskWorkspacePanel from '$lib/components/task-detail/TaskWorkspacePanel.svelte';
  import TaskMetricsPanel from '$lib/components/task-detail/TaskMetricsPanel.svelte';
  import DeveloperSessionPanel from '$lib/components/task-detail/DeveloperSessionPanel.svelte';
  import JobList from '$lib/components/task-detail/JobList.svelte';
  import RunList from '$lib/components/task-detail/RunList.svelte';
  import TaskDependencies from '$lib/components/task-detail/TaskDependencies.svelte';
  import TimelineList from '$lib/components/task-detail/TimelineList.svelte';
  import ValidationList from '$lib/components/task-detail/ValidationList.svelte';
  import { ApiError } from '$lib/api';
  import { startTaskRefresh } from '$lib/services/task-updates';
  import { createLatestRequest, createLiveRefresh } from '$lib/live-refresh';
  import { mergeTaskMessages } from '$lib/task-messages';
  import { safeExternalUrl } from '$lib/task-links';
  import {
    getTask,
    listTaskJobs,
    listTaskRuns,
    listTaskEvents,
    listTaskValidations,
    getTaskMetrics,
    listTaskMessages,
    addTaskMessage,
    runTaskCommand,
    type TaskCommand
  } from '$lib/services/tasks';
  import type {
    Task,
    Job,
    NativeRun,
    TaskEvent,
    ValidationRecord,
    TaskMetrics,
    TaskMessage
  } from '$lib/types';

  let task = $state<Task | null>(null);
  let jobs = $state<Job[]>([]);
  let runs = $state<NativeRun[]>([]);
  let events = $state<TaskEvent[]>([]);
  let validations = $state<ValidationRecord[]>([]);
  let metrics = $state<TaskMetrics | null>(null);
  let messages = $state<TaskMessage[]>([]);
  let cursor = $state<number | null>(null);
  let loadingOlder = $state(false);
  let sending = $state(false);
  let commanding = $state(false);
  let error = $state('');
  let connected = $state(false);
  let activeTaskId = '';
  let missingTaskId = $state('');
  const requests = createLatestRequest();
  let routeTaskId: string | undefined;

  async function refresh() {
    const id = page.params.id ?? '';
    if (missingTaskId === id) return;
    const latest = requests.begin();
    const current = () => page.params.id === id && latest();
    let next: Task;
    try {
      next = await getTask(id);
    } catch (cause) {
      if (!current()) return;
      if (cause instanceof ApiError && cause.status === 404) {
        task = null;
        missingTaskId = id;
        error = '';
        return;
      }
      throw cause;
    }
    if (!current()) return;
    missingTaskId = '';
    const snapshot = await Promise.all([
      listTaskJobs(id),
      listTaskEvents(id),
      listTaskValidations(id),
      getTaskMetrics(id),
      listTaskMessages(id),
      listTaskRuns(id)
    ]).catch((cause) => {
      if (!current()) return null;
      throw cause;
    });
    if (!snapshot || !current()) return;
    const [nextJobs, nextEvents, nextValidations, nextMetrics, notes, nextRuns] = snapshot;
    task = next;
    jobs = nextJobs;
    runs = nextRuns;
    events = nextEvents;
    validations = nextValidations;
    metrics = nextMetrics;
    const knownMessages = new Set(messages.map((message) => message.id));
    if (
      activeTaskId !== id ||
      (notes.next_before_id !== null &&
        !notes.items.some((message) => knownMessages.has(message.id)))
    ) {
      // A burst larger than one page can leave a gap. Restart pagination from
      // the latest page so every intervening message remains reachable.
      messages = notes.items;
      cursor = notes.next_before_id;
      activeTaskId = id;
    } else {
      messages = mergeTaskMessages(messages, notes.items);
    }
  }

  const live = createLiveRefresh(async () => {
    const id = page.params.id;
    try {
      await refresh();
      if (page.params.id === id) error = '';
    } catch (cause) {
      if (page.params.id === id) error = String(cause);
    }
  });
  afterNavigate(() => {
    if (routeTaskId === page.params.id) return;
    routeTaskId = page.params.id;
    requests.invalidate();
    task = null;
    messages = [];
    cursor = null;
    activeTaskId = '';
    missingTaskId = '';
    coordinationMode = 'off';
    sending = commanding = loadingOlder = false;
    error = '';
    live.request();
  });
  onMount(() => {
    return startTaskRefresh(live, {
      taskId: () => page.params.id,
      connected: (value) => {
        connected = value;
        if (value) live.request();
      }
    });
  });

  async function command(action: TaskCommand) {
    if (!task || task.id !== page.params.id || commanding) return;
    const id = task.id;
    commanding = true;
    error = '';
    try {
      await runTaskCommand(id, action);
      if (page.params.id === id) await refresh();
    } catch (cause) {
      if (page.params.id === id) error = String(cause);
    } finally {
      if (page.params.id === id) commanding = false;
    }
  }

  async function send(body: string, replyTo?: number) {
    if (!task || task.id !== page.params.id || sending) return;
    const id = task.id;
    sending = true;
    error = '';
    try {
      await addTaskMessage(id, body, replyTo);
      if (page.params.id !== id) return;
      try {
        await refresh();
      } catch (cause) {
        if (page.params.id === id) error = 'Message saved. Could not refresh: ' + String(cause);
      }
    } catch (cause) {
      if (page.params.id === id) error = String(cause);
      throw cause;
    } finally {
      if (page.params.id === id) sending = false;
    }
  }

  async function older() {
    if (!task || cursor === null || loadingOlder) return;
    loadingOlder = true;
    const requestedTaskId = task.id;
    const requestedCursor = cursor;
    try {
      const notes = await listTaskMessages(requestedTaskId, requestedCursor);
      if (page.params.id !== requestedTaskId || cursor !== requestedCursor) return;
      messages = mergeTaskMessages(messages, notes.items);
      cursor = notes.next_before_id;
    } catch (cause) {
      if (page.params.id === requestedTaskId) error = String(cause);
    } finally {
      if (page.params.id === requestedTaskId) loadingOlder = false;
    }
  }
</script>

<svelte:head><title>{task?.title || 'Task'} · Engineering Worker</title></svelte:head>
<PageHeader
  eyebrow="Engineering task"
  title={missingTaskId === page.params.id
    ? 'Task not found'
    : task?.title || (error ? 'Task unavailable' : 'Loading task')}
  description="One coding session, deterministic validation and delivery, auditable controls."
/>
<main class="grid min-w-0 grid-cols-1 gap-5 p-4 sm:p-6 md:p-10 xl:grid-cols-2">
  <ErrorBanner message={error} class="xl:col-span-2" />
  {#if task}
    <section class="flex flex-wrap items-center gap-3 xl:col-span-2" aria-label="Task summary">
      <strong class="text-brand"
        >{task.status.replaceAll('_', ' ')} · {task.stage.replaceAll('_', ' ')}</strong
      >
      <span class="text-sm text-muted">{task.team_name || 'Unassigned'} · P{task.priority}</span>
      <small class="ml-auto text-muted"
        >{connected ? 'Live updates' : 'Reconnecting · polling every 10 seconds'}</small
      >
      {#if safeExternalUrl(task.source?.url)}
        <!-- eslint-disable svelte/no-navigation-without-resolve -->
        <a
          class="text-sm text-brand underline"
          href={safeExternalUrl(task.source?.url) || ''}
          target="_blank"
          rel="noopener noreferrer">{task.source?.provider} · {task.external_key} ↗</a
        >
        <!-- eslint-enable svelte/no-navigation-without-resolve -->
      {/if}
    </section>
    {#if task.wait_reason !== 'NONE'}
      <p class="rounded-lg border border-warning/40 p-4 text-sm xl:col-span-2">
        Waiting: {task.wait_reason.replaceAll('_', ' ')}. Review the latest event below before
        resuming.
      </p>
    {/if}
    {#key task.id}<CoordinatorPanel
        taskId={task.id}
        onMode={(mode) => (coordinationMode = mode)}
      />{/key}
    <TaskControls {task} {commanding} onTaskCommand={command} />
    {#key task.id}<TaskDependencies {task} onChanged={refresh} />{/key}
    <TaskMetricsPanel {metrics} taskId={task.id} taskTitle={task.title} />
    {#key task.id}<DeveloperSessionPanel taskId={task.id} onChanged={refresh} />{/key}
    <section class="min-w-0 xl:col-span-2">
      {#key task.id}<TaskConversation
          {messages}
          {coordinationMode}
          taskStatus={task.status}
          hasOlder={cursor !== null}
          {loadingOlder}
          {sending}
          onLoadOlder={older}
          onSend={send}
        />{/key}
    </section>
    <section class="min-w-0 rounded-xl border border-line p-5 xl:col-span-2">
      <h2 class="mb-3 font-semibold">Requirements · version {task.requirement_version}</h2>
      <TaskDescription description={task.description} sourceUrl={task.source?.url} />
    </section>
    <TaskWorkspacePanel {task} />
    <ValidationList {validations} />
    <JobList {jobs} />
    <RunList {runs} taskId={task.id} />
    <div class="min-w-0 xl:col-span-2"><TimelineList {events} /></div>
  {:else if missingTaskId === page.params.id}
    <section class="p-5 xl:col-span-2">
      <p class="text-muted">This task was deleted or no longer exists.</p>
      <a class="mt-3 inline-block text-brand underline" href={resolve('/tasks')}>Back to Tasks</a>
    </section>
  {:else if !error}
    <p class="p-5 text-muted">Loading task and execution evidence…</p>
  {/if}
  {#if task}{#key task.id}<TaskResourceBreakdown taskId={task.id} />{/key}{/if}
</main>
