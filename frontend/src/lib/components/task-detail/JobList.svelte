<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { Job } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let { jobs }: { jobs: Job[] } = $props();

  function stateClass(state: string): string {
    if (state === 'RUNNING' || state === 'CLAIMED') return 'text-brand-2';
    if (state === 'SUCCEEDED') return 'text-accent';
    if (state === 'FAILED' || state === 'TIMED_OUT' || state === 'CANCELLED') return 'text-danger';
    if (state === 'RETRY_WAIT') return 'text-warning';
    return 'text-muted';
  }
</script>

<section class="border-line rounded-xl border p-5">
  <h2 class="mb-4 font-semibold">{t('taskDetail.jobs')}</h2>
  {#if jobs.length === 0}
    <p class="text-muted text-sm">{t('taskDetail.noJobsRecorded')}</p>
  {:else}
    <ShowMore items={jobs}>
      {#snippet children(visibleJobs: Job[])}
        {#each visibleJobs as job, index (job.id)}
          <div
            class="border-line border-t py-3 motion-safe:animate-fade-in-up"
            style="animation-delay: {Math.min(index, 10) * 30}ms"
          >
            <div class="flex justify-between">
              <strong>{job.role}</strong><span class="font-mono text-xs">{job.state}</span>
            </div>
            <small class="text-muted">{job.action} · {t('taskDetail.attempt')} {job.attempt}</small>
            {#if job.result}
              <p class="mt-1 text-xs">
                <span class="font-mono text-accent">{job.result.result}</span>
                <span class="text-muted"> · {job.result.summary}</span>
              </p>
            {/if}
            {#if job.retry_not_before}
              <p class="mt-1 text-xs text-warning">
                {t('taskDetail.retryScheduledFor')}
                {new Date(job.retry_not_before).toLocaleString()}
              </p>
            {/if}
            {#if job.failure_reason}
              <p class="text-muted mt-1 line-clamp-2 text-xs" title={job.failure_reason}>
                {job.failure_reason}
              </p>
            {/if}
          </div>
        {/each}
      {/snippet}
    </ShowMore>
  {/if}
</section>
