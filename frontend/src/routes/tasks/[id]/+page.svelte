<script lang="ts">
  import { page } from '$app/state';
  import { SvelteMap } from 'svelte/reactivity';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TaskControls from '$lib/components/task-detail/TaskControls.svelte';
  import TaskConversation from '$lib/components/task-detail/TaskConversation.svelte';
  import TaskDescription from '$lib/components/task-detail/TaskDescription.svelte';
  import TaskWorkspacePanel from '$lib/components/task-detail/TaskWorkspacePanel.svelte';
  import TaskMetricsPanel from '$lib/components/task-detail/TaskMetricsPanel.svelte';
  import DeveloperSessionPanel from '$lib/components/task-detail/DeveloperSessionPanel.svelte';
  import JobList from '$lib/components/task-detail/JobList.svelte';
  import RunList from '$lib/components/task-detail/RunList.svelte';
  import TimelineList from '$lib/components/task-detail/TimelineList.svelte';
  import ValidationList from '$lib/components/task-detail/ValidationList.svelte';
  import { API_URL } from '$lib/api';
  import { createLiveRefresh } from '$lib/live-refresh';
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

  async function refresh() {
    const id = page.params.id ?? '';
    const [next, nextJobs, nextEvents, nextValidations, nextMetrics, notes, nextRuns] =
      await Promise.all([
        getTask(id),
        listTaskJobs(id),
        listTaskEvents(id),
        listTaskValidations(id),
        getTaskMetrics(id),
        listTaskMessages(id),
        listTaskRuns(id)
      ]);
    if (page.params.id !== id) return;
    task = next;
    jobs = nextJobs;
    runs = nextRuns;
    events = nextEvents;
    validations = nextValidations;
    metrics = nextMetrics;
    if (activeTaskId !== id) {
      messages = notes.items;
      cursor = notes.next_before_id;
      activeTaskId = id;
    } else {
      const merged = new SvelteMap(messages.map((message) => [message.id, message]));
      for (const message of notes.items) merged.set(message.id, message);
      messages = [...merged.values()].sort((a, b) => a.id - b.id);
    }
  }

  onMount(() => {
    const live = createLiveRefresh(async () => {
      try {
        await refresh();
        error = '';
      } catch (cause) {
        error = String(cause);
      }
    });
    live.request();
    const stream = new EventSource(API_URL + '/api/v1/events/stream');
    stream.onopen = () => {
      connected = true;
      live.request();
    };
    stream.onerror = () => {
      connected = false;
    };
    stream.addEventListener('update', (event) => {
      try {
        if (JSON.parse(event.data).task_id === page.params.id) live.request();
      } catch {
        /* Ignore malformed event; the bounded poll reconciles it. */
      }
    });
    const timer = setInterval(() => {
      if (!document.hidden) live.request();
    }, 10000);
    return () => {
      live.stop();
      stream.close();
      clearInterval(timer);
    };
  });

  async function command(action: TaskCommand) {
    if (!task || commanding) return;
    commanding = true;
    error = '';
    try {
      await runTaskCommand(task.id, action);
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }

  async function send(body: string, replyTo?: number) {
    if (!task || sending) return;
    sending = true;
    error = '';
    try {
      await addTaskMessage(task.id, body, replyTo);
      await refresh();
    } catch (cause) {
      error = String(cause);
      throw cause;
    } finally {
      sending = false;
    }
  }

  async function older() {
    if (!task || cursor === null || loadingOlder) return;
    loadingOlder = true;
    try {
      const notes = await listTaskMessages(task.id, cursor);
      messages = [...notes.items, ...messages];
      cursor = notes.next_before_id;
    } catch (cause) {
      error = String(cause);
    } finally {
      loadingOlder = false;
    }
  }
</script>

<svelte:head><title>{task?.title || 'Task'} · Engineering Worker</title></svelte:head>
<PageHeader
  eyebrow="Engineering task"
  title={task?.title || 'Loading task'}
  description="One coding session, deterministic validation and delivery, auditable controls."
/>
<main class="grid min-w-0 gap-5 p-4 sm:p-6 md:p-10 xl:grid-cols-2">
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
    <TaskControls {task} {commanding} onTaskCommand={command} />
    <TaskMetricsPanel {metrics} taskId={task.id} taskTitle={task.title} />
    {#key task.id}<DeveloperSessionPanel taskId={task.id} onChanged={refresh} />{/key}
    <section class="min-w-0 xl:col-span-2">
      <TaskConversation
        {messages}
        taskStatus={task.status}
        hasOlder={cursor !== null}
        {loadingOlder}
        {sending}
        onLoadOlder={older}
        onSend={send}
      />
    </section>
    <section class="min-w-0 rounded-xl border border-line p-5 xl:col-span-2">
      <h2 class="mb-3 font-semibold">Requirements · version {task.requirement_version}</h2>
      <TaskDescription description={task.description} sourceUrl={task.source?.url} />
    </section>
    <TaskWorkspacePanel {task} />
    <ValidationList {validations} />
    <JobList {jobs} />
    <RunList {runs} />
    <div class="min-w-0 xl:col-span-2"><TimelineList {events} /></div>
  {:else}
    <p class="p-5 text-muted">Loading task and execution evidence…</p>
  {/if}
</main>
