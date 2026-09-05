<script lang="ts">
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TaskControls from '$lib/components/task-detail/TaskControls.svelte';
  import TaskWorkspacePanel from '$lib/components/task-detail/TaskWorkspacePanel.svelte';
  import TaskPlanPanel from '$lib/components/task-detail/TaskPlanPanel.svelte';
  import JobList from '$lib/components/task-detail/JobList.svelte';
  import TimelineList from '$lib/components/task-detail/TimelineList.svelte';
  import ValidationList from '$lib/components/task-detail/ValidationList.svelte';
  import FindingList from '$lib/components/task-detail/FindingList.svelte';
  import { API_URL } from '$lib/api';
  import { debounce } from '$lib/debounce';
  import { planFromJobs, latestThinkerJob } from '$lib/task-plan';
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
    retryTaskLinearSync
  } from '$lib/services/tasks';
  import type { Job, ReviewFinding, Task, TaskEvent, ValidationRecord } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';
  let task = $state<Task | null>(null);
  let jobs = $state<Job[]>([]);
  let events = $state<TaskEvent[]>([]);
  let validations = $state<ValidationRecord[]>([]);
  let findings = $state<ReviewFinding[]>([]);
  let error = $state('');
  let preparing = $state(false);
  let commanding = $state(false);
  let latestThinker = $derived(latestThinkerJob(jobs));
  let latestPlan = $derived(planFromJobs(jobs));
  async function refresh() {
    const taskId = page.params.id ?? '';
    [task, jobs, events, validations, findings] = await Promise.all([
      getTask(taskId),
      listTaskJobs(taskId),
      listTaskEvents(taskId),
      listTaskValidations(taskId),
      listTaskFindings(taskId)
    ]);
  }
  const refreshOnUpdate = debounce(() => {
    void refresh().catch((cause) => {
      error = String(cause);
    });
  }, 350);

  onMount(() => {
    void refresh().catch((cause) => {
      error = String(cause);
    });
    const stream = new EventSource(`${API_URL}/api/v1/events/stream`);
    stream.addEventListener('update', refreshOnUpdate);
    return () => stream.close();
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
</script>

<PageHeader
  eyebrow={t('taskDetail.eyebrow')}
  title={task?.title || t('taskDetail.loadingTask')}
  description={task?.description || t('taskDetail.defaultDescription')}
/>
<main class="grid gap-6 p-4 sm:p-6 md:p-10 xl:grid-cols-2">
  <ErrorBanner message={error} class="xl:col-span-2" />
  {#if !task}
    <div class="skeleton h-24 rounded-sm xl:col-span-2"></div>
    <div class="skeleton h-16 rounded-sm xl:col-span-2"></div>
    <div class="skeleton h-40 rounded-sm xl:col-span-2"></div>
  {/if}
  {#if task}
    <TaskControls
      {task}
      {commanding}
      onEnqueue={enqueue}
      onTaskCommand={taskCommand}
      onPublishPullRequest={publishPullRequest}
      onMergePullRequest={mergePullRequest}
      onRetryLinearSync={retryLinearSync}
    />
    <TaskWorkspacePanel {task} {preparing} onPrepareWorkspace={prepareWorkspace} />
  {/if}
  <TaskPlanPanel {latestPlan} {latestThinker} />
  <JobList {jobs} />
  <TimelineList {events} />
  <ValidationList {validations} />
  <FindingList {findings} />
</main>
