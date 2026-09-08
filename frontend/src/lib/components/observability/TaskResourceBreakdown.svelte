<script lang="ts">
  import { getTaskResources, getRunnerHistory } from '$lib/services/observability';
  import { getTaskAnalytics } from '$lib/services/analytics';
  import type { RunnerResource, MetricResult, InfrastructureEvent } from '$lib/types/observability';
  import type { TaskAnalytics } from '$lib/types/analytics';
  import EChart from './EChart.svelte';
  import TaskUsageDetails from './TaskUsageDetails.svelte';
  import { bytes, count, duration, money, percent } from './format';
  let { taskId }: { taskId: string } = $props();
  let runners = $state<RunnerResource[]>([]),
    analytics = $state<TaskAnalytics | null>(null);
  let history = $state<MetricResult | null>(null),
    error = $state(''),
    busy = $state(false),
    loaded = $state(false);
  let metric = $state<'cpu' | 'memory'>('memory');
  let events = $state<InfrastructureEvent[]>([]);
  async function load() {
    if (busy) return;
    busy = true;
    try {
      const [resources, usage] = await Promise.all([
        getTaskResources(taskId),
        getTaskAnalytics(taskId)
      ]);
      runners = resources.runners;
      events = resources.events;
      analytics = usage;
      loaded = true;
      error = '';
    } catch {
      error = 'Task analytics unavailable. Existing execution history remains below.';
    } finally {
      busy = false;
    }
  }
  async function selectRunner(id: string) {
    try {
      history = await getRunnerHistory(id, metric);
    } catch {
      history = null;
      error = 'Resource history unavailable.';
    }
  }
</script>

<details
  class="panel"
  ontoggle={(event) => {
    if (event.currentTarget.open && !loaded) void load();
  }}
>
  <summary>AI usage, resources & forecast vs actual</summary>
  <button disabled={busy} onclick={load}>Refresh analytics</button>
  {#if error}<p role="status">{error}</p>{/if}
  {#if analytics}<p>
      Known AI cost {money(analytics.known_cost_usd)} · {analytics.unknown_cost_runs} unknown costs ·
      Input {count(analytics.input_tokens)} / output {count(analytics.output_tokens)}
    </p>
    <p>
      Developer active {duration(analytics.developer_active_seconds)} · Human/external wait {duration(
        analytics.human_or_external_wait_seconds
      )} · Wall time {duration(analytics.wall_seconds)}
    </p>
    <p>
      {analytics.developer_turns} Developer turns · {analytics.compactions} compactions · {analytics.review_cycles}
      repair reviews · {analytics.validation_failures} validation failures
    </p>
    {#each analytics.warnings as warning (warning)}<p class="warning">
        {warning.replaceAll('_', ' ')}
      </p>{/each}
    <TaskUsageDetails {analytics} />
    <details>
      <summary>Completed phase times</summary
      >{#each Object.entries(analytics.phases) as [phase, seconds] (phase)}<p>
          {phase} · {duration(seconds)}
        </p>{/each}
    </details>{/if}
  <label
    >History metric <select
      bind:value={metric}
      onchange={() => {
        history = null;
      }}><option value="memory">Memory</option><option value="cpu">CPU cores</option></select
    ></label
  >
  {#each runners as runner (runner.runner_run_id)}<article>
      <header>
        <strong>{runner.service_kind} · {runner.phase}</strong><button
          onclick={() => selectRunner(runner.runner_run_id)}>View history</button
        >
      </header>
      <p>
        Peak RAM {bytes(runner.summary?.values.max_memory_bytes)} · CPU {runner.summary?.values.cpu_seconds?.toFixed(
          2
        ) ?? 'Unknown'} core-seconds
      </p>
      <p>
        Coverage {percent(runner.summary?.sample_coverage_ratio)} · {runner.summary
          ?.metrics_complete
          ? 'Complete'
          : 'Incomplete / unavailable'} · Exit {runner.exit_code ?? 'Unknown'} · OOM {runner.oom_killed ===
        null
          ? 'Unknown'
          : runner.oom_killed
            ? 'Yes'
            : 'No'}
      </p>
      <details>
        <summary>Network, disk & process summary</summary
        >{#each Object.entries(runner.summary?.values ?? {}) as [key, value] (key)}<p>
            {key.replaceAll('_', ' ')} · {value === null
              ? 'Unavailable'
              : key.includes('bytes')
                ? bytes(value)
                : value.toFixed(2)}
          </p>{/each}
      </details>
    </article>{:else}<p>
      No collected runner resources. Older runs cannot be reconstructed.
    </p>{/each}
  <details>
    <summary>Runner incidents & lifecycle</summary>
    {#each events as event (event.id)}
      <p
        class:warning={event.event_type === 'oom' ||
          (event.exit_code != null && event.exit_code !== 0)}
      >
        {new Date(event.occurred_at).toLocaleString()} · {event.service_name} · {event.event_type}
        {#if event.exit_code != null}
          · Exit {event.exit_code}{/if}
      </p>
    {:else}<p>No recorded runner incidents or lifecycle events for this task.</p>{/each}
  </details>
  {#if history}<EChart
      summary={`${metric} history · ${history.status}. Missing samples are gaps.`}
      option={{
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'time' },
        yAxis: { type: 'value', name: metric === 'memory' ? 'Bytes' : 'Cores' },
        series: history.series.map((s) => ({
          type: 'line',
          showSymbol: false,
          connectNulls: false,
          data: s.samples.map(([at, v]) => [at * 1000, v])
        }))
      }}
    />{/if}
</details>

<style>
  .panel {
    border: 1px solid var(--border, #334155);
    border-radius: 1rem;
    padding: 1rem;
    grid-column: 1/-1;
  }
  summary {
    cursor: pointer;
    padding-block: 0.6rem;
  }
  p {
    margin-block: 0.6rem;
    font-size: 0.85rem;
  }
  article {
    padding: 1rem;
    background: rgb(100 116 139/0.08);
    margin-block: 1rem;
    border-radius: 0.6rem;
  }
  header {
    display: flex;
    gap: 1rem;
    justify-content: space-between;
  }
  button,
  select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border, #334155);
    border-radius: 0.4rem;
  }
  .warning {
    color: #d97706;
  }
</style>
