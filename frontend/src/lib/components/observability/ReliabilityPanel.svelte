<script lang="ts">
  import type { Availability, Incident, LiveMetrics } from '$lib/types/observability';
  import EChart from './EChart.svelte';
  import { duration, percent } from './format';
  import './analytics-panels.css';
  let {
    availability,
    incidents,
    live
  }: { availability: Availability | null; incidents: Incident[]; live: LiveMetrics | null } =
    $props();
</script>

<section class="ops-panel">
  <h3>Availability & incidents</h3>
  <div class="cards">
    {#each availability?.services ?? [] as service (service.service)}<article>
        <small>{service.service} · 30d</small><strong>{percent(service.uptime_ratio)}</strong><span
          >Sample coverage {percent(service.sample_coverage_ratio)}</span
        >
      </article>{:else}<p>
        Availability history unavailable. Missing probes are not downtime.
      </p>{/each}
  </div>
  <EChart
    summary="Endpoint availability: 1 available, 0 confirmed failure. Missing probes remain gaps."
    height={180}
    option={{
      tooltip: { trigger: 'axis' },
      legend: { type: 'scroll' },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', min: 0, max: 1 },
      series: (availability?.services ?? []).map((s) => ({
        name: s.service,
        type: 'line',
        step: 'end',
        showSymbol: false,
        connectNulls: false,
        data: s.samples.map(([at, v]) => [at * 1000, v])
      }))
    }}
  />
  <details>
    <summary>Monitoring target health</summary>
    <div class="cards">
      {#each live?.targets.series ?? [] as target, index (index)}<article>
          <strong>{target.labels.service || target.labels.job}</strong><span
            >{target.samples.at(-1)?.[1] === 1 ? 'Scrape healthy' : 'Scrape unavailable'}</span
          >
        </article>{/each}
    </div>
  </details>
  <div class="scroll">
    <table>
      <thead
        ><tr><th>Service / incident</th><th>Opened</th><th>Duration / state</th><th>Source</th></tr
        ></thead
      ><tbody
        >{#each incidents as incident (incident.id)}<tr
            ><td>{incident.service_key}<small>{incident.kind} · {incident.severity}</small></td><td
              >{new Date(incident.opened_at).toLocaleString()}</td
            ><td
              >{incident.closed_at
                ? duration((Date.parse(incident.closed_at) - Date.parse(incident.opened_at)) / 1000)
                : 'Open'}</td
            ><td>{incident.source}</td></tr
          >{:else}<tr><td colspan="4">No recorded incidents.</td></tr>{/each}</tbody
      >
    </table>
  </div>
  <details>
    <summary>Docker lifecycle history</summary>{#each live?.events ?? [] as event (event.id)}<p
        class="muted"
      >
        <time>{new Date(event.occurred_at).toLocaleString()}</time> · {event.service_name} · {event.event_type}{event.exit_code !==
        null
          ? ` · exit ${event.exit_code}`
          : ''}
      </p>{/each}
  </details>
</section>
