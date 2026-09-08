<script lang="ts">
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import TaskDescription from '$lib/components/task-detail/TaskDescription.svelte';
  import { safeExternalUrl } from '$lib/task-links';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TaskControls from '$lib/components/task-detail/TaskControls.svelte';
  import TaskWorkspacePanel from '$lib/components/task-detail/TaskWorkspacePanel.svelte';
  import TaskPlanPanel from '$lib/components/task-detail/TaskPlanPanel.svelte';
  import JobList from '$lib/components/task-detail/JobList.svelte';
  import TimelineList from '$lib/components/task-detail/TimelineList.svelte';
  import ValidationList from '$lib/components/task-detail/ValidationList.svelte';
  import FindingList from '$lib/components/task-detail/FindingList.svelte';
  import TaskMemoryPanel from '$lib/components/task-detail/TaskMemoryPanel.svelte';
  import TaskMetricsPanel from '$lib/components/task-detail/TaskMetricsPanel.svelte';
  import DeveloperSessionPanel from '$lib/components/task-detail/DeveloperSessionPanel.svelte';
  import GenerationProgress from '$lib/components/task-detail/GenerationProgress.svelte';
  import TaskConversation from '$lib/components/task-detail/TaskConversation.svelte';
  import { API_URL } from '$lib/api';
  import { debounce } from '$lib/debounce';
  import { planFromJobs, latestThinkerJob } from '$lib/task-plan';
  import { taskGenerationProgress } from '$lib/task-generation';
  import {
    getTask,
    listTaskJobs,
    listTaskEvents,
    listTaskValidations,
    listTaskFindings,
    prepareTaskWorkspace,
    createTaskJob,
    runTaskCommand,
    publishTaskPullRequest,
    mergeTaskPullRequest,
    retryTaskLinearSync,
    getTaskMemory,
    listTaskCheckpoints,
    getTaskMetrics,
    listTaskMessages,
    addTaskMessage,
    reactToTaskMessage,
    editTaskMessage,
    deleteTaskMessage
  } from '$lib/services/tasks';
  import type {
    AgentCheckpoint,
    Job,
    ReviewFinding,
    Task,
    TaskEvent,
    TaskMemory,
    TaskMessage,
    ValidationRecord
  } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';
  let task = $state<Task | null>(null);
  let jobs = $state<Job[]>([]);
  let events = $state<TaskEvent[]>([]);
  let validations = $state<ValidationRecord[]>([]);
  let findings = $state<ReviewFinding[]>([]);
  let memory = $state<TaskMemory | null>(null);
  let checkpoints = $state<AgentCheckpoint[]>([]);
  let metrics = $state<import('$lib/types').TaskMetrics | null>(null);
  let messages = $state<TaskMessage[]>([]);
  let nextMessageCursor = $state<number | null>(null);
  let loadingOlderMessages = $state(false);
  let sendingMessage = $state(false);
  let error = $state('');
  let preparing = $state(false);
  let commanding = $state(false);
  let eventStreamConnected = $state(false);
  let latestThinker = $derived(latestThinkerJob(jobs));
  let latestPlan = $derived(planFromJobs(jobs));
  let generationProgress = $derived(taskGenerationProgress(events, jobs));
  async function refresh() {
    const taskId = page.params.id ?? '';
    const [
      nextTask,
      nextJobs,
      nextEvents,
      nextValidations,
      nextFindings,
      nextMemory,
      nextCheckpoints,
      nextMetrics,
      messagePage
    ] = await Promise.all([
      getTask(taskId),
      listTaskJobs(taskId),
      listTaskEvents(taskId),
      listTaskValidations(taskId),
      listTaskFindings(taskId),
      getTaskMemory(taskId),
      listTaskCheckpoints(taskId),
      getTaskMetrics(taskId),
      listTaskMessages(taskId)
    ]);
    task = nextTask;
    jobs = nextJobs;
    events = nextEvents;
    validations = nextValidations;
    findings = nextFindings;
    memory = nextMemory;
    checkpoints = nextCheckpoints;
    metrics = nextMetrics;
    messages = messagePage.items;
    nextMessageCursor = messagePage.next_before_id;
  }
  const refreshOnUpdate = debounce(() => {
    void refresh().catch((cause) => {
      error = String(cause);
    });
  }, 350);

  function handleStreamUpdate(event: MessageEvent<string>) {
    try {
      const message = JSON.parse(event.data) as { task_id?: unknown };
      if (message.task_id !== page.params.id) return;
    } catch {
      return;
    }
    refreshOnUpdate();
  }

  onMount(() => {
    void refresh().catch((cause) => {
      error = String(cause);
    });
    const stream = new EventSource(`${API_URL}/api/v1/events/stream`);
    stream.onopen = () => {
      eventStreamConnected = true;
    };
    stream.onerror = () => {
      eventStreamConnected = false;
    };
    stream.addEventListener('update', handleStreamUpdate);
    return () => {
      eventStreamConnected = false;
      stream.close();
    };
  });
  async function prepareWorkspace() {
    if (!task) return;
    preparing = true;
    error = '';
    try {
      task = await prepareTaskWorkspace(task.id);
      events = await listTaskEvents(task.id);
    } catch (cause) {
      error = String(cause);
    } finally {
      preparing = false;
    }
  }
  async function enqueue(role: 'THINKER' | 'EXECUTOR' | 'REVIEWER', action: string) {
    if (!task) return;
    commanding = true;
    error = '';
    try {
      await createTaskJob(task.id, { role, action, priority: task.priority, payload: {} });
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }
  async function taskCommand(command: 'pause' | 'cancel' | 'takeover' | 'resume') {
    if (!task) return;
    commanding = true;
    try {
      task = await runTaskCommand(task.id, command);
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }
  async function publishPullRequest() {
    if (!task) return;
    commanding = true;
    error = '';
    try {
      await publishTaskPullRequest(task.id);
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }
  async function mergePullRequest() {
    if (!task) return;
    commanding = true;
    error = '';
    try {
      await mergeTaskPullRequest(task.id);
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }
  async function retryLinearSync() {
    if (!task) return;
    commanding = true;
    error = '';
    try {
      await retryTaskLinearSync(task.id);
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }

  async function loadOlderMessages() {
    if (!task || !nextMessageCursor || loadingOlderMessages) return;
    loadingOlderMessages = true;
    try {
      const page = await listTaskMessages(task.id, nextMessageCursor);
      messages = [...page.items, ...messages];
      nextMessageCursor = page.next_before_id;
    } finally {
      loadingOlderMessages = false;
    }
  }

  async function sendMessage(body: string, replyToId?: number) {
    if (!task || sendingMessage) return;
    sendingMessage = true;
    error = '';
    try {
      const message = await addTaskMessage(task.id, body, replyToId);
      messages = [...messages, message];
    } catch (cause) {
      error = String(cause);
      throw cause;
    } finally {
      sendingMessage = false;
    }
  }

  async function reactMessage(messageId: number, reaction: string) {
    if (!task) return;
    const updated = await reactToTaskMessage(task.id, messageId, reaction);
    messages = messages.map((item) => (item.id === messageId ? updated : item));
  }

  async function deleteMessage(messageId: number) {
    if (!task) return;
    await deleteTaskMessage(task.id, messageId);
    const page = await listTaskMessages(task.id);
    messages = page.items;
  }
  async function editMessage(messageId: number, body: string) {
    if (!task) return;
    const updated = await editTaskMessage(task.id, messageId, body);
    messages = messages.map((item) => (item.id === messageId ? updated : item));
  }
</script>

<svelte:head><title>{task?.title || 'Task'} · Engineering Worker</title></svelte:head>
<PageHeader
  eyebrow={t('taskDetail.eyebrow')}
  title={task?.title || t('taskDetail.loadingTask')}
  description="Conversation, progress, and evidence for this task."
/>
<main class="grid gap-6 p-4 sm:p-6 md:p-10 xl:grid-cols-2">
  <ErrorBanner message={error} class="xl:col-span-2" />
  {#if !task}
    <div class="skeleton h-24 rounded-sm xl:col-span-2"></div>
    <div class="skeleton h-16 rounded-sm xl:col-span-2"></div>
    <div class="skeleton h-40 rounded-sm"></div>
    <div class="skeleton h-40 rounded-sm"></div>
    <div class="skeleton h-40 rounded-sm"></div>
    <div class="skeleton h-40 rounded-sm"></div>
  {:else}
    <section class="flex flex-wrap items-center gap-3 xl:col-span-2" aria-label="Task summary">
      <span
        class="rounded-full border border-brand/30 bg-brand/10 px-3 py-1.5 text-xs font-semibold text-brand"
        >{task.state.replaceAll('_', ' ')}</span
      >
      <span class="text-xs text-muted"
        >{task.team_name || 'Unassigned team'} · P{task.priority}</span
      >
      {#if safeExternalUrl(task.source?.url)}
        <!-- eslint-disable svelte/no-navigation-without-resolve -->
        <a
          class="max-w-full truncate text-sm text-brand underline underline-offset-4"
          href={safeExternalUrl(task.source?.url) || ''}
          target="_blank"
          rel="noopener noreferrer"
          >{task.source?.provider} · {task.source?.identifier || task.external_key} ↗</a
        >
        <!-- eslint-enable svelte/no-navigation-without-resolve -->
      {/if}
      <span class="ml-auto flex gap-2">
        {#if ['PAUSED', 'NEEDS_HUMAN', 'CONTEXT_PENDING'].includes(task.state) || task.manual_takeover}
          <Button disabled={commanding} onclick={() => taskCommand('resume')}>Resume work</Button>
        {:else if !['MERGED', 'CANCELLED', 'FAILED'].includes(task.state)}
          <Button disabled={commanding} onclick={() => taskCommand('pause')}>Pause work</Button>
        {/if}
      </span>
    </section>
    <details class="rounded-xl border border-line bg-panel p-4 xl:col-span-2">
      <summary class="cursor-pointer text-sm font-semibold">Automation controls</summary>
      <TaskControls
        {task}
        {commanding}
        onEnqueue={enqueue}
        onTaskCommand={taskCommand}
        onPublishPullRequest={publishPullRequest}
        onMergePullRequest={mergePullRequest}
        onRetryLinearSync={retryLinearSync}
      />
    </details>
    <GenerationProgress progress={generationProgress} connected={eventStreamConnected} />
    <TaskMetricsPanel {metrics} taskId={task.id} taskTitle={task.title} />
    {#key task.id}<DeveloperSessionPanel taskId={task.id} onChanged={refresh} />{/key}
    <div class="min-w-0 xl:col-span-2">
      <TaskConversation
        {messages}
        taskState={task.state}
        resumeOnSend={false}
        hasOlder={nextMessageCursor !== null}
        loadingOlder={loadingOlderMessages}
        sending={sendingMessage}
        onLoadOlder={loadOlderMessages}
        onSend={sendMessage}
        onReact={reactMessage}
        onEdit={editMessage}
        onDelete={deleteMessage}
      />
    </div>
    <details open class="min-w-0 rounded-xl border border-line bg-panel p-5 xl:col-span-2">
      <summary class="mb-3 cursor-pointer text-sm font-semibold">Task description</summary>
      <TaskDescription description={task.description} sourceUrl={task.source?.url} />
    </details>
    <TaskWorkspacePanel {task} {preparing} onPrepareWorkspace={prepareWorkspace} />
    <div class="min-w-0 xl:col-span-2">
      <TaskPlanPanel {latestPlan} {latestThinker} />
    </div>
    <FindingList {findings} />
    <ValidationList {validations} />
    <details class="min-w-0 rounded-xl border border-line bg-panel p-5 xl:col-span-2">
      <summary class="cursor-pointer text-sm font-semibold"
        >Execution history &amp; context <span class="font-normal text-muted"
          >· {jobs.length} jobs · {events.length} events</span
        ></summary
      >
      <div class="mt-4 grid min-w-0 gap-5 xl:grid-cols-2">
        <TaskMemoryPanel {memory} {checkpoints} />
        <JobList {jobs} />
        <TimelineList {events} />
      </div>
    </details>
  {/if}
</main>
