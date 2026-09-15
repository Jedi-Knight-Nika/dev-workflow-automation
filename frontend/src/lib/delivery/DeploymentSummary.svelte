<script lang="ts">
  import type { deploymentMetrics } from './metrics';
  let { metrics }: { metrics: ReturnType<typeof deploymentMetrics> } = $props();
  const elapsed = (value: number) =>
    value < 60000 ? `${Math.round(value / 1000)}s` : `${Math.round(value / 60000)} min`;
</script>

<div class="space-y-2 text-xs" aria-label="Deployment metrics">
  <p>
    {metrics.observed} deployments observed · {metrics.succeeded} succeeded · {metrics.failed} had failures
  </p>
  {#if metrics.meanCompletionMs !== null}<p>
      Average creation → first success: {elapsed(metrics.meanCompletionMs)}
    </p>{/if}
  {#if metrics.meanRecoveryMs !== null}<p>
      Average failure → next success in the same repository/environment: {elapsed(
        metrics.meanRecoveryMs
      )} ({metrics.recoverySamples} intervals)
    </p>{/if}
  {#if metrics.unresolvedEnvironments}<p>
      {metrics.unresolvedEnvironments} environments have an observed failure without a later success in
      this range.
    </p>{/if}
  <p class="text-muted">
    Counts cover the selected observations. A deployment can fail and later succeed. These outcomes
    do not establish production incidents or a change-failure rate.
  </p>
</div>
