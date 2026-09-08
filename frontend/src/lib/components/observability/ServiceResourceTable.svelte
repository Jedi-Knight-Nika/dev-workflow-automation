<script lang="ts">
  import type { ServiceResource, MetricResult } from '$lib/types/observability';
  import { getServiceHistory } from '$lib/services/observability';
  import EChart from './EChart.svelte';
  import { bytes, percent, count, duration } from './format';
  let { services }: { services: ServiceResource[] } = $props();
  let sort = $state<'cpu' | 'memory' | 'network_rx_rate'>('memory');
  let selected = $state(''),
    metric = $state('memory'),
    hours = $state(1);
  let history = $state<MetricResult | null>(null),
    error = $state('');
  const rows = $derived([...services].sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1)));
  $effect(() => {
    const service = selected,
      key = metric,
      window = hours;
    let disposed = false;
    history = null;
    if (service)
      void getServiceHistory(service, key, window)
        .then((value) => {
          if (!disposed) {
            history = value;
            error = '';
          }
        })
        .catch(() => {
          if (!disposed) error = 'History unavailable';
        });
    return () => {
      disposed = true;
    };
  });
</script>

<section>
  <header>
    <h3>Service resource leaderboard ({services.length})</h3>
    <label
      >Sort <select bind:value={sort}
        ><option value="memory">RAM</option><option value="cpu">CPU</option><option
          value="network_rx_rate">Network RX</option
        ></select
      ></label
    >
  </header>
  <div class="scroll">
    <table>
      <thead
        ><tr
          ><th>Service / container</th><th>CPU</th><th>RAM / limit</th><th>Network RX / TX</th><th
            >Restarts / OOM · 7d</th
          ><th>State / health</th><th>Uptime</th><th>PIDs / throttling</th><th>Last seen</th></tr
        ></thead
      >
      <tbody
        >{#each rows as row (row.id)}<tr
            ><td
              >{#if row.service}<button
                  onclick={() => (selected = selected === row.service ? '' : (row.service ?? ''))}
                  >{row.service}</button
                >{:else}{row.name}{/if}<small>{row.name}</small></td
            ><td>{percent(row.cpu)}<small>{row.cpu?.toFixed(2) ?? 'Unknown'} cores</small></td><td
              >{bytes(row.memory)}<small
                >{row.memory_limit === 0 ? 'No limit' : bytes(row.memory_limit)} · {percent(
                  row.memory_ratio
                )}</small
              ></td
            ><td>{bytes(row.network_rx_rate)}/s<small>{bytes(row.network_tx_rate)}/s</small></td><td
              >{count(row.restart_count)} / {count(row.oom_count)}</td
            ><td>{row.state ?? 'Unknown'}<small>{row.health ?? 'Unknown'}</small></td><td
              >{duration(row.uptime_seconds)}</td
            ><td>{count(row.pids)}<small>{percent(row.throttled_rate)}</small></td><td
              >{row.last_seen ? new Date(row.last_seen * 1000).toLocaleTimeString() : 'Unknown'}</td
            ></tr
          >{:else}<tr><td colspan="9">No current container samples.</td></tr>{/each}</tbody
      >
    </table>
  </div>
  {#if selected}<div class="history">
      <header>
        <h4>{selected} history</h4>
        <label
          >Metric <select bind:value={metric}
            ><option value="memory">RAM</option><option value="cpu">CPU cores</option><option
              value="network_rx_rate">Network RX bytes/s</option
            ><option value="network_tx_rate">Network TX bytes/s</option><option
              value="block_read_rate">Disk read bytes/s</option
            ><option value="block_write_rate">Disk write bytes/s</option></select
          ></label
        ><label
          >Window <select bind:value={hours}
            ><option value={1}>1 hour</option><option value={24}>24 hours</option><option
              value={168}>7 days</option
            ></select
          ></label
        ><button onclick={() => (selected = '')}>Close history</button>
      </header>
      {#if error}<p role="status">{error}</p>{/if}
      {#if history}<EChart
          summary={`${selected} ${metric} · ${history.status}. Missing samples remain gaps.`}
          option={{
            tooltip: { trigger: 'axis' },
            legend: { type: 'scroll' },
            xAxis: { type: 'time' },
            yAxis: { type: 'value' },
            series: history.series.map((row) => ({
              name: row.labels.name,
              type: 'line',
              showSymbol: false,
              connectNulls: false,
              data: row.samples.map(([at, value]) => [at * 1000, value])
            }))
          }}
        />{/if}
    </div>{/if}
</section>

<style>
  section {
    min-width: 0;
  }
  header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    align-items: center;
  }
  h3 {
    font-size: 1rem;
    color: var(--color-heading);
  }
  .scroll {
    overflow: auto;
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }
  th,
  td {
    text-align: left;
    padding: 0.8rem;
    border-bottom: 1px solid var(--color-line);
    white-space: nowrap;
  }
  th {
    color: var(--color-muted);
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    background: var(--color-panel-alt);
  }
  tbody tr {
    transition: background-color 0.2s var(--ease-smooth);
  }
  tbody tr:hover {
    background: color-mix(in srgb, var(--color-brand-2) 6%, transparent);
  }
  small {
    display: block;
    opacity: 0.7;
    font-size: 0.7rem;
    color: var(--color-muted);
  }
  select,
  button {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    color: var(--color-text);
  }
  select:focus,
  button:focus-visible {
    border-color: var(--color-brand-2);
    outline: none;
  }
  td button {
    border: none;
    padding: 0;
    background: none;
    color: var(--color-brand-2);
    cursor: pointer;
  }
  td button:hover {
    text-shadow: 0 0 10px color-mix(in srgb, var(--color-brand-2) 55%, transparent);
  }
  .history {
    padding-top: 1rem;
    border-top: 1px solid var(--color-line);
  }
</style>
