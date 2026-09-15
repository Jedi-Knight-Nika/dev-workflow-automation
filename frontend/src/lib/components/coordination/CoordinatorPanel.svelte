<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getCoordination,
    reconcileAction,
    reviewAction,
    type Coordination
  } from '$lib/services/coordination';
  import { startTaskRefresh } from '$lib/services/task-updates';
  import { createLiveRefresh } from '$lib/live-refresh';
  import HumanRequestCard from './HumanRequestCard.svelte';
  let { taskId, onMode }: { taskId: string; onMode: (mode: Coordination['mode']) => void } =
    $props();
  let coordination = $state<Coordination | null>(null),
    error = $state(''),
    checking = $state<string | null>(null);
  let disposed = false;
  const refresh = createLiveRefresh(async () => {
    try {
      const next = await getCoordination(taskId);
      if (disposed) return;
      coordination = next;
      onMode(coordination.mode);
      error = '';
    } catch (cause) {
      error = String(cause);
    }
  });
  async function runAction(actionId: string, operation: () => Promise<unknown>) {
    if (checking) return;
    checking = actionId;
    try {
      await operation();
      refresh.request();
    } catch (cause) {
      error = String(cause);
    } finally {
      checking = null;
    }
  }
  onMount(() => {
    const stop = startTaskRefresh(refresh, { taskId: () => taskId });
    return () => {
      disposed = true;
      stop();
    };
  });
</script>

{#if error}<p role="alert" class="col-span-full text-sm text-danger">{error}</p>{/if}
{#if coordination && coordination.mode !== 'off'}
  <section class="col-span-full space-y-3" aria-label="Task coordination">
    {#if coordination.human_request && coordination.mode === 'active'}{#key coordination.human_request.id}<HumanRequestCard
          request={coordination.human_request}
          onAnswered={() => refresh.request()}
        />{/key}{/if}
    {#if coordination.mode === 'shadow'}<p class="text-sm text-muted">
        Coordinator is observing. Proposed actions do not change tasks or send messages.
      </p>{/if}
    {#each coordination.actions.filter( (action) => ['REJECTED', 'UNKNOWN', 'RECONCILING', 'WAITING_ENGINEER'].includes(action.status) ) as action (action.id)}<p
        role="status"
        class="rounded border border-warning/40 p-3 text-sm"
      >
        {action.type}: {action.status === 'RECONCILING'
          ? 'Checking provider history…'
          : action.error}
        {#if action.status === 'UNKNOWN' && action.type !== 'REQUEST_REVIEW'}
          <button
            type="button"
            class="ml-2 underline"
            disabled={checking !== null}
            onclick={() => void runAction(action.id, () => reconcileAction(taskId, action.id))}
            >Check delivery</button
          >
        {/if}
      </p>{/each}
    <details class="rounded-xl border border-line p-4">
      <summary class="cursor-pointer text-sm">Coordinator activity</summary>
      <div class="mt-3 space-y-3">
        {#each coordination.actions as action (action.id)}
          <article class="rounded border border-line p-3 text-sm">
            <p>{action.type.toLowerCase().replaceAll('_', ' ')} · {action.status.toLowerCase()}</p>
            <p class="mt-1 text-xs text-muted">Was this an appropriate action?</p>
            <div class="mt-2 flex gap-3">
              <button
                class="text-xs underline"
                aria-pressed={action.review === 'CORRECT'}
                disabled={checking !== null}
                onclick={() =>
                  void runAction(action.id, () => reviewAction(taskId, action.id, 'CORRECT'))}
                >Appropriate{action.review === 'CORRECT' ? ' ✓' : ''}</button
              >
              <button
                class="text-xs underline"
                aria-pressed={action.review === 'INCORRECT'}
                disabled={checking !== null}
                onclick={() =>
                  void runAction(action.id, () => reviewAction(taskId, action.id, 'INCORRECT'))}
                >Incorrect{action.review === 'INCORRECT' ? ' ✓' : ''}</button
              >
            </div>
          </article>
        {/each}
        {#each coordination.runs as run (run.id)}<article class="border-l border-line pl-3 text-sm">
            <p class="text-muted">{new Date(run.created_at).toLocaleString()} · {run.status}</p>
            <p>{run.decision?.reason || run.error || 'Reading task context…'}</p>
          </article>{:else}<p class="text-sm text-muted">No conversations processed yet.</p>{/each}
      </div>
    </details>
  </section>
{/if}
