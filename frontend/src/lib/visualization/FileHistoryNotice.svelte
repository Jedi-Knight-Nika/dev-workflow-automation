<script lang="ts">
  import type { FileHistory } from './types';
  let { history }: { history: FileHistory | undefined } = $props();
  const names: Record<string, string> = {
    COMPLETE: 'collected',
    PENDING: 'pending',
    UNAVAILABLE: 'commit unavailable',
    MISSING_WORKSPACE: 'workspace unavailable',
    TOO_LARGE: 'over collection limit',
    INVALID: 'unreadable',
    EXPIRED: 'detail expired'
  };
</script>

{#if history}
  <p class:incomplete={history.incomplete || history.collection_enabled === false}>
    File history: {#each Object.entries(history.counts) as [status, count] (status)}<span
        >{count} {names[status] ?? 'unknown'} ·
      </span>{/each}
    {history.collection_enabled === false
      ? 'collection disabled.'
      : 'collected validated commits only.'}
    {#if history.sampled}
      Coverage counts are sampled; narrow the range for exact counts.{/if}
  </p>
{/if}

<style>
  p {
    padding: 0.4rem 1rem;
    margin: 0;
    flex-shrink: 0;
    font-size: 0.72rem;
    color: var(--color-muted);
  }
  .incomplete {
    color: var(--color-warning);
  }
</style>
