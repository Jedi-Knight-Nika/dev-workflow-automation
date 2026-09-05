<script lang="ts">
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import PageHeader from '$lib/PageHeader.svelte';
  import { API_URL, api } from '$lib/api';
  import type { Job, ReviewFinding, Task, TaskEvent, ValidationRecord } from '$lib/types';
  let task = $state<Task | null>(null);
  let jobs = $state<Job[]>([]);
  let events = $state<TaskEvent[]>([]);
  let validations = $state<ValidationRecord[]>([]);
  let findings = $state<ReviewFinding[]>([]);
  let error = $state('');
  let preparing = $state(false);
  let commanding = $state(false);
  type ThinkerPlan = {
    goal: string;
    targets: string[];
    ordered_steps: string[];
    constraints: string[];
    required_tests: string[];
    risks: string[];
    acceptance_criteria: string[];
  };
  function isStringArray(value: unknown): value is string[] {
    return Array.isArray(value) && value.every((item) => typeof item === 'string');
  }
  function planFromJobs(currentJobs: Job[]): ThinkerPlan | null {
    const data = [...currentJobs]
      .reverse()
      .find((job) => job.role === 'THINKER' && job.state === 'SUCCEEDED' && job.result)
      ?.result?.data;
    if (
      !data ||
      typeof data.goal !== 'string' ||
      !isStringArray(data.targets) ||
      !isStringArray(data.ordered_steps) ||
      !isStringArray(data.constraints) ||
      !isStringArray(data.required_tests) ||
      !isStringArray(data.risks) ||
      !isStringArray(data.acceptance_criteria)
    )
      return null;
    return data as ThinkerPlan;
  }
  let latestThinker = $derived(
    [...jobs].reverse().find((job) => job.role === 'THINKER' && job.state === 'SUCCEEDED') ?? null
  );
  let latestPlan = $derived(planFromJobs(jobs));
  async function refresh() {
    [task, jobs, events, validations, findings] = await Promise.all([
      api<Task>(`/tasks/${page.params.id}`),
      api<Job[]>(`/tasks/${page.params.id}/jobs`),
      api<TaskEvent[]>(`/tasks/${page.params.id}/events`),
      api<ValidationRecord[]>(`/tasks/${page.params.id}/validations`),
      api<ReviewFinding[]>(`/tasks/${page.params.id}/findings`)
    ]);
  }
  onMount(() => {
    void refresh().catch((cause) => {
      error = String(cause);
    });
    const stream = new EventSource(`${API_URL}/api/v1/events/stream`);
    stream.addEventListener('update', () => {
      void refresh().catch((cause) => {
        error = String(cause);
      });
    });
    return () => stream.close();
  });
  async function prepareWorkspace() {
    if (!task) return;
    preparing = true;
    error = '';
    try {
      task = await api<Task>(`/tasks/${task.id}/workspace`, { method: 'POST' });
      events = await api<TaskEvent[]>(`/tasks/${task.id}/events`);
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
      await api<Job>(`/tasks/${task.id}/jobs`, {
        method: 'POST',
        body: JSON.stringify({ role, action, priority: task.priority, payload: {} })
      });
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
      task = await api<Task>(`/tasks/${task.id}/${command}`, { method: 'POST' });
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
      await api(`/tasks/${task.id}/pull-request`, { method: 'POST' });
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
      await api(`/tasks/${task.id}/merge`, { method: 'POST' });
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
      await api(`/tasks/${task.id}/linear-sync`, { method: 'POST' });
      await refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      commanding = false;
    }
  }
</script>

<PageHeader
  eyebrow="TASK DETAIL"
  title={task?.title || 'Loading task…'}
  description={task?.description || 'Plan, jobs, and complete event history.'}
/>
<main class="grid gap-6 p-6 md:p-10 xl:grid-cols-2">
  {#if error}<p class="bg-red-950 p-3 text-red-300 xl:col-span-2">{error}</p>{/if}
  {#if task}
    <section class="border-line flex flex-wrap items-center gap-2 border p-5 xl:col-span-2">
      <strong class="mr-auto">Task controls</strong>
      {#if task.manual_takeover}<span
          class="border border-amber-700 px-2 py-1 font-mono text-[10px] text-amber-300"
          >MANUAL CONTROL</span
        >{/if}
      <button
        class="border-line border px-3 py-2 text-xs disabled:opacity-30"
        disabled={commanding || task.manual_takeover}
        onclick={() => enqueue('THINKER', 'CREATE_PLAN')}>Plan</button
      >
      <button
        class="border-line border px-3 py-2 text-xs disabled:opacity-30"
        disabled={commanding || task.manual_takeover || !task.repository_id}
        onclick={() => enqueue('EXECUTOR', 'IMPLEMENT_PLAN')}>Implement</button
      >
      <button
        class="border-line border px-3 py-2 text-xs disabled:opacity-30"
        disabled={commanding || task.manual_takeover || !task.workspace_path}
        onclick={() => enqueue('REVIEWER', 'REVIEW_CHANGES')}>Review</button
      >
      <button
        class="border-line border px-3 py-2 text-xs disabled:opacity-30"
        disabled={commanding || task.manual_takeover || !task.workspace_path}
        onclick={publishPullRequest}>{task.pull_request_number ? 'Update PR' : 'Publish PR'}</button
      >
      <button
        class="border border-emerald-800 px-3 py-2 text-xs text-emerald-300 disabled:opacity-30"
        disabled={commanding ||
          task.manual_takeover ||
          !task.pull_request_number ||
          task.state === 'MERGED'}
        onclick={mergePullRequest}>Merge</button
      >
      {#if task.state === 'MERGED' && task.external_key}<button
          class="border-line border px-3 py-2 text-xs disabled:opacity-30"
          disabled={commanding}
          onclick={retryLinearSync}>Retry Linear sync</button
        >{/if}
      {#if task.manual_takeover}<button
          class="border border-amber-700 px-3 py-2 text-xs text-amber-300 disabled:opacity-30"
          disabled={commanding}
          onclick={() => taskCommand('resume')}>Resume automation</button
        >{:else}<button
          class="border border-amber-700 px-3 py-2 text-xs text-amber-300 disabled:opacity-30"
          disabled={commanding || task.state === 'MERGED' || task.state === 'CANCELLED'}
          onclick={() => taskCommand('takeover')}>Take over manually</button
        >{/if}
      <button
        class="border-line border px-3 py-2 text-xs disabled:opacity-30"
        disabled={commanding || task.manual_takeover}
        onclick={() => taskCommand('pause')}>Pause</button
      >
      <button
        class="border border-red-900 px-3 py-2 text-xs text-red-300 disabled:opacity-30"
        disabled={commanding}
        onclick={() => taskCommand('cancel')}>Cancel</button
      >
    </section>
    <section class="border-line flex items-center justify-between border p-5 xl:col-span-2">
      <div>
        <strong>Git workspace</strong>
        <p class="text-muted text-xs">
          {task.workspace_path ||
            (task.repository_id
              ? 'Repository selected; workspace not prepared.'
              : 'No repository selected for this task.')}
        </p>
        {#if task.branch_name}<p class="mt-1 font-mono text-[10px] text-accent">
            {task.branch_name} · {task.current_revision?.slice(0, 12)}
          </p>{/if}
        {#if task.pull_request_url}<!-- eslint-disable svelte/no-navigation-without-resolve -->
          <a
            class="mt-2 block text-xs text-accent underline"
            href={task.pull_request_url}
            target="_blank"
            rel="noreferrer">Pull request #{task.pull_request_number}</a
          ><!-- eslint-enable svelte/no-navigation-without-resolve -->{/if}
      </div>
      <button
        class="border-line border px-3 py-2 text-xs disabled:opacity-30"
        disabled={!task.repository_id || preparing}
        onclick={prepareWorkspace}
        >{preparing
          ? 'Preparing…'
          : task.workspace_path
            ? 'Refresh workspace'
            : 'Prepare workspace'}</button
      >
    </section>
  {/if}
  <section class="border-line border p-5 xl:col-span-2">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h2 class="font-semibold">Latest technical plan</h2>
      {#if latestPlan}<span class="font-mono text-[10px] text-emerald-300">PLAN READY</span>{/if}
    </div>
    {#if latestPlan}
      <h3 class="text-lg font-medium">{latestPlan.goal}</h3>
      {#if latestPlan.targets.length}<p class="text-muted mt-2 text-xs">
          Targets: {latestPlan.targets.join(', ')}
        </p>{/if}
      <div class="mt-5 grid gap-5 md:grid-cols-2">
        <div>
          <h3 class="mb-2 text-xs font-semibold tracking-wider text-accent uppercase">Steps</h3>
          <ol class="text-muted list-decimal space-y-1 pl-5 text-sm">
            {#each latestPlan.ordered_steps as step, index (index)}<li>{step}</li>{/each}
          </ol>
        </div>
        <div>
          <h3 class="mb-2 text-xs font-semibold tracking-wider text-accent uppercase">
            Acceptance criteria
          </h3>
          <ul class="text-muted list-disc space-y-1 pl-5 text-sm">
            {#each latestPlan.acceptance_criteria as criterion, index (index)}<li>
                {criterion}
              </li>{/each}
          </ul>
        </div>
        <div>
          <h3 class="mb-2 text-xs font-semibold tracking-wider uppercase">Required tests</h3>
          <ul class="text-muted list-disc space-y-1 pl-5 text-sm">
            {#each latestPlan.required_tests as test, index (index)}<li>{test}</li>{/each}
          </ul>
        </div>
        <div>
          <h3 class="mb-2 text-xs font-semibold tracking-wider uppercase">Constraints and risks</h3>
          <ul class="text-muted list-disc space-y-1 pl-5 text-sm">
            {#each [...latestPlan.constraints, ...latestPlan.risks] as item, index (index)}<li>
                {item}
              </li>{/each}
          </ul>
        </div>
      </div>
    {:else if latestThinker?.result?.result === 'NEEDS_CONTEXT'}
      <p class="text-sm text-amber-300">
        The Thinker needs more context: {String(latestThinker.result.data.reason || 'Unspecified')}
      </p>
      {#if isStringArray(latestThinker.result.data.questions)}
        <ul class="text-muted mt-3 list-disc space-y-1 pl-5 text-sm">
          {#each latestThinker.result.data.questions as question, index (index)}<li>
              {question}
            </li>{/each}
        </ul>
      {/if}
    {:else if latestThinker?.result?.result === 'NEEDS_HUMAN'}
      <p class="text-sm text-amber-300">
        Human decision required: {String(latestThinker.result.data.reason || 'Unspecified')}
      </p>
    {:else}
      <p class="text-muted text-sm">No successful Thinker plan has been produced yet.</p>
    {/if}
  </section>
  <section class="border-line border p-5">
    <h2 class="mb-4 font-semibold">Jobs</h2>
    {#each jobs as job (job.id)}<div class="border-line border-t py-3">
        <div class="flex justify-between">
          <strong>{job.role}</strong><span class="font-mono text-xs">{job.state}</span>
        </div>
        <small class="text-muted">{job.action} · attempt {job.attempt}</small>
        {#if job.result}
          <p class="mt-1 text-xs">
            <span class="font-mono text-accent">{job.result.result}</span>
            <span class="text-muted"> · {job.result.summary}</span>
          </p>
        {/if}
        {#if job.retry_not_before}
          <p class="mt-1 text-xs text-amber-300">
            Retry scheduled for {new Date(job.retry_not_before).toLocaleString()}
          </p>
        {/if}
        {#if job.failure_reason}
          <p class="text-muted mt-1 line-clamp-2 text-xs" title={job.failure_reason}>
            {job.failure_reason}
          </p>
        {/if}
      </div>{:else}<p class="text-muted text-sm">No jobs recorded.</p>{/each}
  </section>
  <section class="border-line border p-5">
    <h2 class="mb-4 font-semibold">Timeline</h2>
    {#each events as event (event.id)}<div class="border-line border-l pb-5 pl-4">
        <strong class="text-sm">{event.event_type.replaceAll('_', ' ')}</strong>
        <p class="text-muted text-xs">
          {event.source} · {new Date(event.created_at).toLocaleString()}
        </p>
      </div>{:else}<p class="text-muted text-sm">No events recorded.</p>{/each}
  </section>
  <section class="border-line border p-5 xl:col-span-2">
    <h2 class="mb-4 font-semibold">GitHub validation</h2>
    {#each validations as validation (validation.id)}<div class="border-line border-t py-3">
        <div class="flex justify-between gap-3">
          <strong class="text-sm">{validation.name}</strong>
          <span class="font-mono text-xs">{validation.status}</span>
        </div>
        <small class="text-muted">{validation.kind} · {validation.revision.slice(0, 12)}</small>
        {#if validation.details_url}<!-- eslint-disable svelte/no-navigation-without-resolve -->
          <a
            class="ml-3 text-xs text-accent underline"
            href={validation.details_url}
            target="_blank"
            rel="noreferrer">Open evidence</a
          ><!-- eslint-enable svelte/no-navigation-without-resolve -->{/if}
      </div>{:else}<p class="text-muted text-sm">No check or review evidence received.</p>{/each}
  </section>
  <section class="border-line border p-5 xl:col-span-2">
    <h2 class="mb-4 font-semibold">Internal review findings</h2>
    {#each findings as finding (finding.id)}<article class="border-line border-t py-3">
        <div class="flex flex-wrap justify-between gap-3">
          <strong class="text-sm"
            >{finding.severity} · {finding.status}{finding.occurrence_count > 1
              ? ` · repeated ${finding.occurrence_count}×`
              : ''}</strong
          >
          <span class="text-muted font-mono text-[10px]"
            >{finding.workspace_fingerprint.slice(0, 12)}</span
          >
        </div>
        <p class="mt-1 text-sm">{finding.message}</p>
        {#if finding.file_path}<p class="text-muted mt-1 font-mono text-xs">
            {finding.file_path}{finding.line ? `:${finding.line}` : ''}
          </p>{/if}
      </article>{:else}<p class="text-muted text-sm">No internal findings recorded.</p>{/each}
  </section>
</main>
