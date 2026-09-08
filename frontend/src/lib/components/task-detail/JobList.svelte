<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { Job } from '$lib/types';
  let { jobs }: { jobs: Job[] } = $props();
</script>

<section class="border-line rounded-xl border p-5">
  <h2 class="mb-4 font-semibold">Execution jobs</h2>
  {#if !jobs.length}<p class="text-muted text-sm">No jobs recorded.</p>{/if}
  <ShowMore items={jobs}>
    {#snippet children(visible: Job[])}
      {#each visible as job (job.id)}
        <article class="border-line space-y-1 border-t py-3 text-sm">
          <div class="flex justify-between gap-3">
            <strong>{job.action.replaceAll('_', ' ')}</strong><span class="font-mono text-xs"
              >{job.state}</span
            >
          </div>
          <p class="text-muted text-xs">
            Attempt {job.attempt} · Worker {job.worker_id ?? 'unassigned'}
          </p>
          <p class="text-muted text-xs">
            Queued {new Date(job.created_at).toLocaleString()}{job.started_at
              ? ' · Started ' + new Date(job.started_at).toLocaleString()
              : ''}{job.finished_at
              ? ' · Finished ' + new Date(job.finished_at).toLocaleString()
              : ''}
          </p>
          {#if job.retry_not_before}<p class="text-warning text-xs">
              Retry after {new Date(job.retry_not_before).toLocaleString()}
            </p>{/if}
          {#if job.failure_reason}<p class="break-words text-warning">{job.failure_reason}</p>{/if}
        </article>
      {/each}
    {/snippet}
  </ShowMore>
</section>
