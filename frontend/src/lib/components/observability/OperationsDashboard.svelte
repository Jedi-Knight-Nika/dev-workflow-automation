<script lang="ts">
  import { onMount } from 'svelte';
  import { operations, subscribeOperations } from '$lib/services/live-operations.svelte';
  import {
    getIncidents,
    getAvailability,
    getMonitoringSettings
  } from '$lib/services/observability';
  import {
    getAnalytics,
    getQueueForecast,
    getPeriodForecast,
    getForecastAccuracy
  } from '$lib/services/analytics';
  import type { Incident, Availability, MonitoringSettings } from '$lib/types/observability';
  import type { AnalyticsDashboard, CostForecast, ForecastAccuracy } from '$lib/types/analytics';
  import MetricGauge from './MetricGauge.svelte';
  import RingGauge from './RingGauge.svelte';
  import RunnerResourceCard from './RunnerResourceCard.svelte';
  import ServiceResourceTable from './ServiceResourceTable.svelte';
  import AnalyticsPanels from './AnalyticsPanels.svelte';
  import ForecastPanels from './ForecastPanels.svelte';
  import ReliabilityPanel from './ReliabilityPanel.svelte';
  import { bytes, count, duration, money } from './format';
  let { teamId }: { teamId?: string } = $props();
  const live = $derived(operations.live);
  let analytics = $state<AnalyticsDashboard | null>(null),
    incidents = $state<Incident[]>([]);
  let availability = $state<Availability | null>(null),
    config = $state<MonitoringSettings | null>(null);
  let forecasts = $state<(CostForecast | null)[]>([]),
    accuracy = $state<ForecastAccuracy | null>(null);
  let error = $state(''),
    days = $state(30),
    refreshVersion = $state(0);
  const runners = $derived(
    (live?.active_runners ?? []).filter((r) => !teamId || r.team_id === teamId)
  );
  const budgetRatio = $derived(
    config?.monthly_budget_usd && analytics?.month_totals
      ? ((Number(analytics.month_totals.known_cost_usd) +
          Number(analytics.month_totals.reserved_usd)) /
          config.monthly_budget_usd) *
          100
      : null
  );
  onMount(subscribeOperations);
  $effect(() => {
    const window = days,
      team = teamId;
    void refreshVersion;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      if (!document.hidden) {
        const result = await Promise.allSettled([
          getAnalytics(window, team),
          getIncidents(),
          getAvailability(),
          getMonitoringSettings(),
          getQueueForecast(team),
          getPeriodForecast(7),
          getPeriodForecast(30),
          getForecastAccuracy()
        ]);
        if (!stopped) {
          analytics = result[0].status === 'fulfilled' ? result[0].value : null;
          error = analytics ? '' : 'AI analytics unavailable';
          incidents = result[1].status === 'fulfilled' ? result[1].value : [];
          availability = result[2].status === 'fulfilled' ? result[2].value : null;
          config = result[3].status === 'fulfilled' ? result[3].value : null;
          forecasts = result
            .slice(4, 7)
            .map((r) => (r.status === 'fulfilled' ? (r.value as CostForecast) : null));
          accuracy = result[7].status === 'fulfilled' ? result[7].value : null;
        }
      }
      if (!stopped) timer = setTimeout(refresh, 30000);
    };
    void refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  });
</script>

<section class="operations" aria-label="Live operations and AI analytics">
  <header>
    <div>
      <p class="eyebrow">V2.1 · Operations</p>
      <h2>System & engineering intelligence</h2>
    </div>
    <label
      >AI window <select bind:value={days}
        ><option value={1}>24 hours</option><option value={7}>7 days</option><option value={30}
          >30 days</option
        ></select
      ></label
    ><button onclick={() => refreshVersion++}>Refresh analytics</button>
  </header>
  <p class="muted">
    {live?.sampled_at
      ? `Metrics sampled ${new Date(live.sampled_at).toLocaleTimeString()}`
      : 'Infrastructure monitoring unavailable or disabled.'} · {live?.status ?? 'unavailable'}
  </p>
  {#if error || operations.error}<p role="status">{error || operations.error}</p>{/if}
  {#if !teamId}
    <div class="gauges">
      <MetricGauge
        label="Host CPU"
        value={live?.host.host_cpu ?? null}
        warning={config?.cpu_warning}
      /><MetricGauge
        label="Host RAM"
        value={live?.host.host_memory ?? null}
        warning={config?.ram_warning}
      /><MetricGauge label="Monthly AI budget" value={budgetRatio} /><RingGauge
        label="Disk"
        value={live?.host.host_disk ?? null}
        warning={config?.disk_warning}
      />
    </div>
    <p class="muted">
      Host uptime {duration(live?.host.host_uptime)} · {live?.services.length ?? 0} containers · {runners.length}
      active runners · Budget {money(config?.monthly_budget_usd)} includes known spend and reservations;
      unknown costs remain flagged. Docker Desktop readings describe its Linux VM.
    </p>
    <details>
      <summary>Host capacity & throughput</summary>
      <div class="kpis">
        <article>
          <small>RAM available / total</small><strong
            >{bytes(live?.host.host_memory_available)} / {bytes(
              live?.host.host_memory_total
            )}</strong
          ><span>Swap {bytes(live?.host.host_swap)}</span>
        </article>
        <article>
          <small>Load · 1 / 5 / 15 minutes</small><strong
            >{live?.host.host_load1?.toFixed(2) ?? 'Unavailable'} / {live?.host.host_load5?.toFixed(
              2
            ) ?? 'Unavailable'} / {live?.host.host_load15?.toFixed(2) ?? 'Unavailable'}</strong
          ><span>File descriptors {count(live?.host.host_file_descriptors)}</span>
        </article>
        <article>
          <small>Disk free / growth</small><strong>{bytes(live?.host.host_disk_available)}</strong
          ><span
            >{bytes(live?.host.host_disk_growth)}/s · Busy {live?.host.host_disk_busy?.toFixed(1) ??
              'Unknown'}%</span
          >
        </article>
        <article>
          <small>Disk read / write</small><strong
            >{bytes(live?.host.host_disk_read)}/s / {bytes(live?.host.host_disk_write)}/s</strong
          >
        </article>
        <article>
          <small>Network RX / TX</small><strong
            >{bytes(live?.host.host_network_rx)}/s / {bytes(live?.host.host_network_tx)}/s</strong
          ><span
            >Errors {count(live?.host.host_network_errors)}/s · Drops {count(
              live?.host.host_network_drops
            )}/s</span
          >
        </article>
        <article>
          <small>Last boot / last observed</small><strong
            >{live?.host.host_boot_time
              ? new Date(live.host.host_boot_time * 1000).toLocaleString()
              : 'Unknown'}</strong
          ><span
            >{live?.host.host_last_seen
              ? new Date(live.host.host_last_seen * 1000).toLocaleTimeString()
              : 'Unknown'}</span
          >
        </article>
      </div>
    </details>
    <ServiceResourceTable services={live?.services ?? []} />
  {/if}
  {#if analytics}<AnalyticsPanels {analytics} {days} />{/if}
  <ForecastPanels {forecasts} {accuracy} />
  <h3>Active runners ({runners.length})</h3>
  <div class="kpis">
    {#each runners as runner (runner.runner_run_id)}<RunnerResourceCard {runner} />{:else}<p>
        No observed active runners.
      </p>{/each}
  </div>
  {#if !teamId}<ReliabilityPanel {availability} {incidents} {live} />{/if}
</section>

<style>
  .operations {
    display: grid;
    gap: 1.2rem;
    min-width: 0;
    padding: 1.5rem;
    border: 1px solid var(--color-line);
    border-radius: 1.25rem;
    grid-column: 1/-1;
    position: relative;
    background:
      radial-gradient(
        circle at 0% 0%,
        color-mix(in srgb, var(--color-brand) 7%, transparent),
        transparent 55%
      ),
      radial-gradient(
        circle at 100% 100%,
        color-mix(in srgb, var(--color-brand-2) 6%, transparent),
        transparent 55%
      ),
      var(--color-panel-alt);
    box-shadow: 0 0 40px -20px color-mix(in srgb, var(--color-brand-2) 35%, transparent);
  }
  header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    align-items: center;
  }
  h2 {
    font-size: 1.4rem;
    font-weight: 700;
    background-image: linear-gradient(90deg, var(--color-brand-2), var(--color-brand));
    background-clip: text;
    -webkit-background-clip: text;
    color: transparent;
  }
  h3 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-heading);
  }
  .eyebrow {
    color: var(--color-brand-2);
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    font-weight: 600;
    text-shadow: 0 0 12px color-mix(in srgb, var(--color-brand-2) 55%, transparent);
  }
  .gauges,
  .kpis {
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  }
  .kpis article {
    display: grid;
    gap: 0.4rem;
    align-content: start;
    padding: 1rem;
    border-radius: 0.9rem;
    background: var(--color-panel);
    border: 1px solid var(--color-line);
    transition:
      border-color 0.3s var(--ease-smooth),
      box-shadow 0.3s var(--ease-smooth),
      transform 0.3s var(--ease-smooth);
  }
  .kpis article:hover {
    border-color: color-mix(in srgb, var(--color-brand-2) 50%, var(--color-line));
    box-shadow: 0 0 20px -6px color-mix(in srgb, var(--color-brand-2) 40%, transparent);
    transform: translateY(-2px);
  }
  .kpis strong {
    font-size: 1.1rem;
    overflow-wrap: anywhere;
    color: var(--color-heading);
  }
  small,
  .muted,
  span {
    font-size: 0.8rem;
    opacity: 0.75;
    color: var(--color-muted);
  }
  select,
  button {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    color: var(--color-text);
  }
  header button {
    border-color: var(--color-brand);
    background: color-mix(in srgb, var(--color-brand) 14%, var(--color-input));
    cursor: pointer;
    font-weight: 600;
    transition:
      box-shadow 0.25s var(--ease-smooth),
      transform 0.12s var(--ease-smooth);
  }
  header button:hover {
    box-shadow: 0 0 18px -4px color-mix(in srgb, var(--color-brand) 60%, transparent);
  }
  select:focus,
  button:focus-visible {
    outline: none;
    border-color: var(--color-brand-2);
  }
  summary {
    cursor: pointer;
    padding: 0.5rem 0;
    color: var(--color-brand-2);
  }
  summary:hover {
    text-shadow: 0 0 10px color-mix(in srgb, var(--color-brand-2) 55%, transparent);
  }
  details {
    min-width: 0;
  }
  @media (max-width: 600px) {
    .operations {
      padding: 0.8rem;
    }
  }
</style>
