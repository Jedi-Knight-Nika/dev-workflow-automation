<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import { API_URL } from '$lib/api';
  import { debounce } from '$lib/debounce';
  import Button from '$lib/components/Button.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import ShowMore from '$lib/components/ShowMore.svelte';
  import Card from '$lib/components/Card.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import TextArea from '$lib/components/TextArea.svelte';
  import Select from '$lib/components/Select.svelte';
  import { tasksResource } from '$lib/stores/tasks.svelte';
  import { repositoriesResource } from '$lib/stores/repositories.svelte';
  import { integrationsResource, webhookHealthResource } from '$lib/stores/integrations.svelte';
  import { createTask as createTaskRequest } from '$lib/services/tasks';
  import { listWorkers } from '$lib/services/workers';
  import { getDashboardActivity } from '$lib/services/dashboard';
  import { t } from '$lib/i18n/index.svelte';
  import type { DashboardActivity, Task, WorkerNode } from '$lib/types';
  import type { TranslationKey } from '$lib/i18n/en';

  let workers: WorkerNode[] = [];
  let activity: DashboardActivity = { active_job: null, queued_jobs: [] };
  let repositoryId = '';
  let title = '';
  let description = '';
  let error = '';

  async function loadWorkers() {
    workers = await listWorkers();
  }

  async function loadActivity() {
    activity = await getDashboardActivity();
  }

  async function createTask(event: SubmitEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    try {
      await createTaskRequest({
        title,
        description,
        priority: 3,
        repository_id: repositoryId || null,
        enqueue_planning: false
      });
    } catch (cause) {
      error = cause instanceof Error ? cause.message : t('dashboard.couldNotQueueTask');
      return;
    }
    title = '';
    description = '';
    repositoryId = '';
    await tasksResource.refresh();
  }

  function dashboardGroups(): Array<{ labelKey: TranslationKey; tasks: Task[] }> {
    const tasks = tasksResource.data;
    const queuedTasks = activity.queued_jobs
      .map((job) => tasks.find((task) => task.id === job.task_id))
      .filter((task): task is Task => task !== undefined);
    return [
      { labelKey: 'dashboard.prioritizedQueue', tasks: queuedTasks },
      {
        labelKey: 'dashboard.waitingReady',
        tasks: tasks.filter((task) => ['WAITING_GITHUB', 'READY_TO_MERGE'].includes(task.state))
      },
      {
        labelKey: 'dashboard.recentlyCompleted',
        tasks: tasks.filter((task) => task.state === 'MERGED').slice(0, 6)
      }
    ];
  }

  const refreshOnUpdate = debounce(() => {
    tasksResource.refresh();
    repositoriesResource.refresh();
    integrationsResource.refresh();
    webhookHealthResource.refresh();
    loadActivity();
  }, 350);

  onMount(() => {
    tasksResource.load();
    repositoriesResource.load();
    integrationsResource.load();
    webhookHealthResource.load();
    loadWorkers();
    loadActivity();
    const events = new EventSource(`${API_URL}/api/v1/events/stream`);
    events.addEventListener('update', refreshOnUpdate);
    events.onerror = () => {
      error = t('dashboard.liveConnectionInterrupted');
    };
    return () => events.close();
  });
</script>

<svelte:head><title>{t('dashboard.pageTitle')}</title></svelte:head>

<header
  class="border-line bg-panel-alt relative flex h-14 items-center justify-end overflow-hidden border-b bg-[radial-gradient(circle_at_10%_0%,color-mix(in_srgb,var(--color-brand)_16%,transparent),transparent_55%),radial-gradient(circle_at_95%_120%,color-mix(in_srgb,var(--color-brand-2)_14%,transparent),transparent_55%)] px-4 md:h-[72px] md:justify-between md:px-6"
>
  <div
    class="relative mx-auto flex w-full max-w-[1180px] items-center justify-end md:justify-between"
  >
    <div class="hidden items-center gap-3 md:flex">
      <span
        class="border-brand neon-glow relative flex size-[38px] shrink-0 overflow-hidden rounded-xl border motion-safe:animate-face-breathe"
      >
        <img src="/logo-face.png" alt="" class="absolute inset-0 h-full w-full object-cover" />
      </span>
      <div class="flex flex-col">
        <strong>{t('nav.brandName')}</strong>
        <small class="text-[11px] tracking-[.12em] text-muted uppercase"
          >{t('nav.controlCenter')}</small
        >
      </div>
    </div>
    <div class="text-muted flex items-center gap-2 text-xs">
      <i
        class="size-[7px] rounded-full {workers.some((worker) => worker.online)
          ? 'bg-accent shadow-[0_0_12px_var(--color-accent)]'
          : 'bg-warning'}"
      ></i>
      {workers.some((worker) => worker.online)
        ? t('dashboard.workerOnline', {
            count: workers.filter((worker) => worker.online).length
          })
        : t('dashboard.noWorkerHeartbeat')}
    </div>
  </div>
</header>

<main class="mx-auto max-w-[1180px] px-4 py-8 sm:px-6 sm:py-10 md:py-16">
  <section class="grid items-start gap-8 xl:grid-cols-[1fr_460px] xl:gap-20">
    <div>
      <p class="text-brand mb-3.5 font-mono text-[11px] font-bold tracking-[.18em]">
        {t('dashboard.eyebrow')}
      </p>
      <h1
        class="text-gradient-brand max-w-[600px] text-[32px] leading-[1.05] font-bold tracking-[-.03em] motion-safe:animate-gradient-shift sm:text-[42px] sm:leading-[1.02] sm:tracking-[-.045em] md:text-[58px]"
      >
        {t('dashboard.heroTitle')}
      </h1>
      <blockquote
        class="border-brand/40 text-muted mt-4 max-w-[550px] border-l-2 pl-4 text-[14px] leading-[1.65] italic sm:text-[15px]"
      >
        “{t('dashboard.heroQuote')}”
      </blockquote>
    </div>
    <form
      class="bg-panel rounded-xl p-5 sm:p-6 sm:shadow-[12px_12px_0_color-mix(in_srgb,var(--color-brand)_55%,transparent)]"
      onsubmit={createTask}
    >
      <div class="mb-3 flex items-center justify-between gap-3">
        <label class="block text-xs font-bold" for="task-title">Manual task</label>
        <span class="text-muted font-mono text-[10px]">UNASSIGNED</span>
      </div>
      <div class="mb-2.5 space-y-2.5">
        <TextField
          id="task-title"
          bind:value={title}
          placeholder={t('dashboard.newTaskPlaceholder')}
          maxlength={500}
        />
        <TextArea
          bind:value={description}
          placeholder={t('dashboard.descriptionPlaceholder')}
          class="h-[90px]"
        />
        <Select bind:value={repositoryId} ariaLabel={t('repositories.title')}>
          <option value="">{t('dashboard.noRepositorySelected')}</option>
          {#each repositoriesResource.data as repository (repository.id)}
            <option value={repository.id}>{repository.owner}/{repository.name}</option>
          {/each}
        </Select>
      </div>
      <p class="text-muted mb-3 text-xs">
        Create it here, then assign an AI team from Task management.
      </p>
      <Button variant="primary" size="lg" type="submit" class="flex w-full justify-between"
        >Create manual task <span>→</span></Button
      >
    </form>
  </section>

  <section class="border-line mb-16 rounded-xl border p-4 sm:p-5">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p class="text-brand mb-2 font-mono text-[11px] font-bold tracking-[.18em]">
          {t('dashboard.workerFleetEyebrow')}
        </p>
        <h2 class="m-0 text-xl font-bold">{t('dashboard.executionCapacity')}</h2>
      </div>
      <Button variant="ghost" onclick={loadWorkers}>{t('common.refresh')}</Button>
    </div>
    {#if workers.length === 0}
      <p class="text-muted mt-4 text-sm">{t('dashboard.noWorkerRegistered')}</p>
    {:else}
      <div class="mt-4 grid gap-2">
        {#each workers as worker, index (worker.id)}
          <div
            class="border-line rounded-lg flex flex-wrap items-center justify-between gap-3 border p-3 text-sm motion-safe:animate-fade-in-up"
            style="animation-delay: {index * 40}ms"
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
                  : 'text-warning'}"
                >{worker.online ? t('dashboard.online') : t('dashboard.offline')}</span
              >
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <section
    class="border-line my-16 grid grid-cols-2 overflow-hidden rounded-xl border lg:grid-cols-4"
  >
    {#each [[tasksResource.data.length, 'dashboard.totalTasks'], [tasksResource.data.filter( (t) => ['PLANNING', 'IMPLEMENTING', 'INTERNAL_REVIEW'].includes(t.state) ).length, 'dashboard.active'], [tasksResource.data.filter((t) => t.state === 'WAITING_GITHUB').length, 'dashboard.waiting'], [tasksResource.data.filter( (t) => ['CONTEXT_PENDING', 'NEEDS_HUMAN'].includes(t.state) ).length, 'dashboard.needsAttention']] as [count, labelKey], index (labelKey)}
      <div
        class:border-r={index % 2 === 0}
        class:border-b={index < 2}
        class="border-line flex flex-col p-4 sm:p-6 lg:border-r lg:border-b-0 last:lg:border-r-0 motion-safe:animate-fade-in-up"
        style="animation-delay: {index * 40}ms"
      >
        <b class="font-mono text-[26px] font-medium sm:text-[32px]">{count}</b>
        <span class="mt-1 text-xs text-muted">{t(labelKey as TranslationKey)}</span>
      </div>
    {/each}
  </section>

  <section class="mb-16 grid gap-4 lg:grid-cols-3">
    <Card hover class="motion-safe:animate-fade-in-up">
      <p class="text-brand font-mono text-[10px] tracking-widest">
        {t('dashboard.currentlyWorking')}
      </p>
      {#if activity.active_job}
        {@const activeTask = tasksResource.data.find(
          (task) => task.id === activity.active_job?.task_id
        )}
        <a
          class="mt-3 block hover:text-brand"
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
      {:else}<p class="text-muted mt-3 text-sm">{t('dashboard.executionLaneIdle')}</p>{/if}
    </Card>
    <Card hover class="motion-safe:animate-fade-in-up" style="animation-delay: 60ms">
      <p class="text-brand font-mono text-[10px] tracking-widest">
        {t('dashboard.integrationHealth')}
      </p>
      {#each integrationsResource.data.filter( (item) => ['github', 'linear'].includes(item.provider_name) ) as integration (integration.id)}
        {@const hook = webhookHealthResource.data.find(
          (item) => item.provider === integration.provider_name
        )}
        <div class="border-line mt-3 flex justify-between border-b pb-2 text-xs">
          <span>{integration.provider_name.toUpperCase()}</span>
          <span
            class={hook?.failed
              ? 'text-danger'
              : integration.status === 'CONNECTED'
                ? 'text-accent'
                : 'text-warning'}
            >{integration.status} · {hook?.pending || 0} pending · {hook?.failed || 0} failed</span
          >
        </div>
      {:else}<p class="text-muted mt-3 text-sm">{t('dashboard.noIntegrationsConfigured')}</p>{/each}
    </Card>
    <Card hover class="motion-safe:animate-fade-in-up" style="animation-delay: 120ms">
      <p class="text-brand font-mono text-[10px] tracking-widest">{t('dashboard.indexHealth')}</p>
      <p class="mt-3 text-2xl font-mono">
        {repositoriesResource.data.filter((repository) => repository.index_status === 'READY')
          .length}/{repositoriesResource.data.length}
      </p>
      <p class="text-muted text-xs">{t('dashboard.reposReadyForRetrieval')}</p>
      {#if repositoriesResource.data.some((repository) => repository.index_status === 'FAILED')}
        <p class="mt-2 text-xs text-danger">
          {t('dashboard.indexFailuresNeedAttention', {
            count: repositoriesResource.data.filter(
              (repository) => repository.index_status === 'FAILED'
            ).length
          })}
        </p>
      {/if}
    </Card>
  </section>

  <section class="mb-16 grid gap-5 lg:grid-cols-3">
    {#each dashboardGroups() as group (group.labelKey)}
      <Card hover>
        <p class="text-brand mb-3 font-mono text-[10px] tracking-widest">{t(group.labelKey)}</p>
        {#each group.tasks as task, index (`${group.labelKey}-${task.id}-${index}`)}
          <a
            class="border-line flex justify-between gap-3 border-b py-2 text-xs transition-colors hover:text-brand motion-safe:animate-fade-in-up"
            style="animation-delay: {index * 30}ms"
            href={resolve('/tasks/[id]', { id: task.id })}
          >
            <span>P{task.priority} · {task.external_key || task.title}</span><span
              >{task.state.replaceAll('_', ' ')}</span
            >
          </a>
        {:else}<p class="text-muted text-sm">{t('common.none')}</p>{/each}
      </Card>
    {/each}
  </section>

  <section>
    <div class="flex items-end justify-between">
      <div>
        <p class="text-brand mb-3.5 font-mono text-[11px] font-bold tracking-[.18em]">
          {t('dashboard.currentWorkEyebrow')}
        </p>
        <h2 class="m-0 text-[22px] font-bold sm:text-[27px]">{t('dashboard.taskQueue')}</h2>
      </div>
      <Button variant="ghost" onclick={() => tasksResource.refresh()}>{t('common.refresh')}</Button>
    </div>
    <ErrorBanner message={error || tasksResource.error} class="mt-5" />
    {#if tasksResource.loading && tasksResource.data.length === 0}
      <div class="border-line mt-5 overflow-hidden rounded-xl border">
        <!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
        {#each Array(4) as _, index (index)}
          <div
            class="border-line grid grid-cols-[40px_1fr] items-center gap-5 border-b px-1 py-5 md:grid-cols-[55px_1fr_auto]"
          >
            <Skeleton class="h-4 w-6" />
            <div class="flex flex-col gap-2">
              <Skeleton class="h-3 w-24" />
              <Skeleton class="h-4 w-48" />
            </div>
            <Skeleton class="col-start-2 h-6 w-28 md:col-start-auto" />
          </div>
        {/each}
      </div>
    {:else if tasksResource.data.length === 0}
      <EmptyState
        variant="panel"
        title={t('dashboard.laneIsClear')}
        message={t('dashboard.queueFirstTask')}
      />
    {:else}
      <div class="border-line mt-5 overflow-hidden rounded-xl border">
        <ShowMore items={tasksResource.data}>
          {#snippet children(visibleTasks: Task[])}
            {#each visibleTasks as task, index (task.id)}
              <article
                class="border-line grid grid-cols-[40px_1fr] items-center gap-5 border-b px-1 py-5 motion-safe:animate-fade-in-up md:grid-cols-[55px_1fr_auto]"
                style="animation-delay: {Math.min(index, 10) * 30}ms"
              >
                <div class="text-brand font-mono text-xs font-bold">P{task.priority}</div>
                <div>
                  <small class="font-mono text-[11px] text-muted"
                    >{task.external_key || task.id.slice(0, 8)}</small
                  >
                  <h3 class="my-1 text-base font-semibold">{task.title}</h3>
                  <p class="m-0 text-[13px] text-muted">
                    {task.description || t('dashboard.noAdditionalContext')}
                  </p>
                </div>
                <div
                  class="border-line col-start-2 justify-self-start rounded-full border px-2.5 py-1.5 font-mono text-[10px] font-bold tracking-[.08em] text-muted md:col-start-auto {task.state ===
                  'NEEDS_HUMAN'
                    ? 'border-warning/40 text-warning'
                    : ''}"
                >
                  {task.state.replaceAll('_', ' ')}
                </div>
              </article>
            {/each}
          {/snippet}
        </ShowMore>
      </div>
    {/if}
  </section>
</main>
