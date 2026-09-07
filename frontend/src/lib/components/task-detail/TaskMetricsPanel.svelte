<script lang="ts">
  import type { TaskMetrics } from '$lib/types';
  let { metrics }: { metrics: TaskMetrics | null } = $props();
  const number = new Intl.NumberFormat();
  function duration(ms: number): string {
    const seconds = Math.round(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return minutes < 60
      ? `${minutes}m ${seconds % 60}s`
      : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }
</script>

<section class="metrics-panel" aria-label="Task execution metrics">
  <div class="mb-4 flex items-start justify-between gap-3">
    <div>
      <h2 class="text-sm font-semibold">Execution metrics</h2>
      <p class="text-muted mt-1 text-xs">Resources consumed by this task’s AI runs.</p>
    </div>
    {#if metrics?.missing_usage_attempts}<span class="text-warning text-[11px]"
        >{metrics.missing_usage_attempts} attempt(s) missing usage</span
      >{/if}
  </div>
  {#if !metrics || metrics.attempts === 0}<p class="text-muted text-sm">
      No AI execution recorded yet.
    </p>{:else}
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <div class="metric"><span>Provider time</span><b>{duration(metrics.duration_ms)}</b></div>
      <div class="metric"><span>AI attempts</span><b>{number.format(metrics.attempts)}</b></div>
      <div class="metric">
        <span>Input tokens</span><b>{number.format(metrics.input_tokens)}</b>
      </div>
      <div class="metric">
        <span>Output tokens</span><b>{number.format(metrics.output_tokens)}</b>
      </div>
      <div class="metric">
        <span>Estimated cost</span><b
          >{metrics.estimated_cost_usd == null
            ? 'Unavailable'
            : `$${metrics.estimated_cost_usd.toFixed(4)}`}</b
        >
      </div>
    </div>
    <div class="mt-5 overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead
          ><tr
            ><th>Role</th><th>Provider / model</th><th>Attempts</th><th>Tokens</th><th>Time</th></tr
          ></thead
        ><tbody
          >{#each metrics.roles as role (role.role + role.provider + role.model)}<tr
              ><td class="font-medium">{role.role}</td><td>{role.provider} / {role.model}</td><td
                >{number.format(role.attempts)}</td
              ><td>{number.format(role.input_tokens + role.output_tokens)}</td><td
                >{duration(role.duration_ms)}</td
              ></tr
            >{/each}</tbody
        >
      </table>
    </div>
  {/if}
</section>

<style>
  .metrics-panel {
    grid-column: 1 / -1;
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    background: var(--color-panel);
    padding: 1.25rem;
  }
  .metric {
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    padding: 0.75rem;
  }
  .metric span {
    display: block;
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .metric b {
    display: block;
    margin-top: 0.3rem;
    font-size: 1rem;
  }
  th {
    color: var(--color-muted);
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.5rem;
  }
  td {
    border-top: 1px solid var(--color-line);
    padding: 0.6rem 0.5rem;
    white-space: nowrap;
  }
</style>
