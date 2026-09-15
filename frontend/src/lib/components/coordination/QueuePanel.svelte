<script lang="ts">
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import { getQueue, setTaskPriority, type WorkQueue } from '$lib/services/coordination';
  import { startTaskRefresh } from '$lib/services/task-updates';
  import { createLiveRefresh } from '$lib/live-refresh';
  import HumanRequestCard from './HumanRequestCard.svelte';
  let { teamId }: { teamId?: string } = $props();
  let queue = $state<WorkQueue | null>(null),
    error = $state('');
  let changing = $state('');
  let offset = $state(0);
  const lanes = [
    ['RUNNING', 'Working'],
    ['QUEUED', 'Queued'],
    ['NEEDS_YOU', 'Needs you'],
    ['WAITING_EXTERNAL', 'Waiting externally'],
    ['BACKLOG', 'Backlog']
  ];
  const refresh = createLiveRefresh(async () => {
    try {
      queue = await getQueue(teamId, offset);
      error = '';
    } catch (cause) {
      error = String(cause);
    }
  });
  onMount(() => startTaskRefresh(refresh));
  async function reprioritize(id: string, value: string) {
    changing = id;
    try {
      await setTaskPriority(id, Number(value));
      refresh.request();
    } catch (cause) {
      error = String(cause);
    } finally {
      changing = '';
    }
  }
</script>

<section
  class="col-span-full space-y-4 rounded-xl border border-line bg-panel p-5"
  aria-label="Engineering queue"
>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h2 class="font-semibold">Engineering queue</h2>
    {#if queue}<p class="text-sm text-muted">
        {teamId ? 'Team Developer slots' : 'Global Developer slots'}
        {queue.developer_slots.busy} / {queue.developer_slots.capacity} · {queue.total}
        open tasks
      </p>{/if}
    <button class="btn-secondary" onclick={() => refresh.request()}>Refresh</button>
  </div>
  {#if error}<p role="alert" class="text-sm text-danger">{error}</p>{/if}
  {#if queue}
    <p class="text-sm text-muted">
      AI spending today: {queue.spending.today_usd === null
        ? 'Awaiting usage'
        : '$' + Number(queue.spending.today_usd).toFixed(2)} · This month: {queue.spending
        .month_usd === null
        ? 'Awaiting usage'
        : '$' + Number(queue.spending.month_usd).toFixed(2)}{queue.spending.monthly_limit_usd
        ? ' / $' + queue.spending.monthly_limit_usd
        : ''}
    </p>
    {#if queue.spending.daily_allowance_exceeded}<p class="text-sm text-warning">
        The Team has exceeded its soft daily allowance.
      </p>{/if}
    {#if queue.human_requests.length && queue.mode === 'active'}
      <div class="grid gap-3 lg:grid-cols-2">
        {#each queue.human_requests as request (request.id)}<div class="space-y-2">
            <a
              class="text-sm text-brand underline"
              href={resolve('/tasks/[id]', { id: request.task_id })}>Open task</a
            ><HumanRequestCard {request} onAnswered={() => refresh.request()} />
          </div>{/each}
      </div>
    {/if}
    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {#each lanes as [lane, label] (lane)}
        {@const entries = queue.entries.filter((entry) => entry.lane === lane)}
        <div class="min-w-0 max-h-96 space-y-2 overflow-y-auto">
          <h3 class="text-sm font-medium">
            {label} <span class="text-muted">{entries.length}</span>
          </h3>
          {#each entries as entry (entry.id)}
            <article class="rounded-lg border border-line p-3">
              <a class="block text-sm text-brand" href={resolve('/tasks/[id]', { id: entry.id })}
                >{entry.title}</a
              >
              <p class="mt-1 text-xs text-muted">
                {entry.team || 'Unassigned'} · {entry.stage.toLowerCase().replaceAll('_', ' ')}
              </p>
              {#if lane === 'QUEUED' || lane === 'BACKLOG'}<label class="mt-2 block text-xs"
                  >Priority
                  <select
                    class="input ml-2"
                    value={entry.priority}
                    disabled={changing === entry.id}
                    onchange={(event) => void reprioritize(entry.id, event.currentTarget.value)}
                  >
                    {#each ['Urgent', 'Critical', 'High', 'Medium', 'Low', 'No priority'] as priority, index (index)}<option
                        value={index}>{priority}</option
                      >{/each}
                  </select></label
                >{/if}
            </article>
          {:else}<p class="text-xs text-muted">No tasks</p>{/each}
        </div>
      {/each}
      <div class="min-w-0 max-h-96 space-y-2 overflow-y-auto">
        <h3 class="text-sm font-medium">
          Recently completed <span class="text-muted">{queue.recently_completed.length}</span>
        </h3>
        <p class="text-xs text-muted">Latest 20 merged tasks from the past week</p>
        {#each queue.recently_completed as entry (entry.id)}
          <article class="rounded-lg border border-line p-3">
            <a class="block text-sm text-brand" href={resolve('/tasks/[id]', { id: entry.id })}
              >{entry.title}</a
            >
            <p class="mt-1 text-xs text-muted">
              {entry.team || 'Unassigned'} · {new Date(entry.completed_at).toLocaleDateString()}
            </p>
          </article>
        {:else}<p class="text-xs text-muted">No completed tasks this week</p>{/each}
      </div>
    </div>
    {#if offset > 0 || queue.truncated}<div class="flex gap-3">
        <button
          class="btn-secondary"
          disabled={offset === 0}
          onclick={() => {
            offset = Math.max(0, offset - 200);
            refresh.request();
          }}>Previous</button
        >
        <span class="text-sm text-muted"
          >{offset + 1}–{offset + queue.entries.length} of {queue.total}</span
        >
        <button
          class="btn-secondary"
          disabled={!queue.truncated}
          onclick={() => {
            offset += 200;
            refresh.request();
          }}>Next</button
        >
      </div>{/if}
  {:else if !error}<p class="text-sm text-muted">Loading queue…</p>{/if}
</section>
