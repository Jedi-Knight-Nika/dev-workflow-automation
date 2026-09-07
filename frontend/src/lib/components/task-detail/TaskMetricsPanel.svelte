<script lang="ts">
  import type { TaskMetrics } from '$lib/types';
  let {
    metrics,
    taskId = 'task',
    taskTitle = 'execution'
  }: { metrics: TaskMetrics | null; taskId?: string; taskTitle?: string } = $props();
  const number = new Intl.NumberFormat();
  function duration(ms: number): string {
    const seconds = Math.round(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return minutes < 60
      ? `${minutes}m ${seconds % 60}s`
      : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }

  function csvCell(value: string | number | null): string {
    const text = value == null ? '' : String(value);
    return `"${text.replaceAll('"', '""')}"`;
  }

  function exportCsv(): void {
    if (!metrics) return;
    const rows: (string | number | null)[][] = [
      ['Task ID', taskId],
      ['Task title', taskTitle],
      ['Exported at', new Date().toISOString()],
      ['Provider time (ms)', metrics.duration_ms],
      ['AI attempts', metrics.attempts],
      ['Input tokens', metrics.input_tokens],
      ['Output tokens', metrics.output_tokens],
      ['Estimated cost (USD)', metrics.estimated_cost_usd],
      [],
      ['Role', 'Provider', 'Model', 'Attempts', 'Input tokens', 'Output tokens', 'Duration (ms)'],
      ...metrics.roles.map((role) => [
        role.role,
        role.provider,
        role.model,
        role.attempts,
        role.input_tokens,
        role.output_tokens,
        role.duration_ms
      ])
    ];
    const csv = rows.map((row) => row.map(csvCell).join(',')).join('\n');
    const blob = new Blob([`\uFEFF${csv}\n`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const stamp = new Date()
      .toISOString()
      .replaceAll(':', '-')
      .replace(/\.\d{3}Z$/, 'Z');
    const slug =
      taskTitle
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .slice(0, 48) || 'execution';
    const link = document.createElement('a');
    link.href = url;
    link.download = `task-${taskId.slice(0, 8)}-${slug}-${stamp}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
</script>

<section class="metrics-panel" aria-label="Task execution metrics">
  <div class="mb-4 flex items-start justify-between gap-3">
    <div>
      <h2 class="text-sm font-semibold">Execution metrics</h2>
      <p class="text-muted mt-1 text-xs">Resources consumed by this task’s AI runs.</p>
    </div>
    <div class="flex items-center gap-3">
      {#if metrics?.missing_usage_attempts}<span class="text-warning text-[11px]"
          >{metrics.missing_usage_attempts} attempt(s) missing usage</span
        >{/if}
      {#if metrics && metrics.attempts > 0}
        <button class="export-button" type="button" onclick={exportCsv}>Export CSV</button>
      {/if}
    </div>
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
  .export-button {
    border: 1px solid var(--color-line);
    border-radius: 0.45rem;
    padding: 0.35rem 0.55rem;
    color: var(--color-muted);
    font-size: 0.68rem;
    transition:
      border-color 120ms ease,
      color 120ms ease;
  }
  .export-button:hover {
    border-color: var(--color-brand);
    color: var(--color-heading);
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
