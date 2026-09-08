<script lang="ts">
  import type { Availability, Incident, LiveMetrics } from '$lib/types/observability';
  import EChart from './EChart.svelte';
  import { duration, percent } from './format';
  import { t } from '$lib/i18n/index.svelte';
  import './analytics-panels.css';
  let {
    availability,
    incidents,
    live
  }: { availability: Availability | null; incidents: Incident[]; live: LiveMetrics | null } =
    $props();
</script>

<section class="ops-panel">
  <h3>{t('operations.availabilityIncidents')}</h3>
  <div class="cards">
    {#each availability?.services ?? [] as service (service.service)}<article>
        <small>{t('operations.uptimeWindow', { service: service.service })}</small><strong
          >{percent(service.uptime_ratio)}</strong
        ><span
          >{t('operations.sampleCoverage', { value: percent(service.sample_coverage_ratio) })}</span
        >
      </article>{:else}<p>
        {t('operations.availabilityUnavailable')}
      </p>{/each}
  </div>
  <EChart
    summary={t('operations.endpointAvailabilitySummary')}
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
    <summary>{t('operations.monitoringTargetHealth')}</summary>
    <div class="cards">
      {#each live?.targets.series ?? [] as target, index (index)}<article>
          <strong>{target.labels.service || target.labels.job}</strong><span
            >{target.samples.at(-1)?.[1] === 1
              ? t('operations.scrapeHealthy')
              : t('operations.scrapeUnavailable')}</span
          >
        </article>{/each}
    </div>
  </details>
  <div class="scroll">
    <table>
      <thead
        ><tr
          ><th>{t('operations.colServiceIncident')}</th><th>{t('operations.colOpened')}</th><th
            >{t('operations.colDurationState')}</th
          ><th>{t('operations.colSource')}</th></tr
        ></thead
      ><tbody
        >{#each incidents as incident (incident.id)}<tr
            ><td>{incident.service_key}<small>{incident.kind} · {incident.severity}</small></td><td
              >{new Date(incident.opened_at).toLocaleString()}</td
            ><td
              >{incident.closed_at
                ? duration((Date.parse(incident.closed_at) - Date.parse(incident.opened_at)) / 1000)
                : t('operations.incidentOpen')}</td
            ><td>{incident.source}</td></tr
          >{:else}<tr><td colspan="4">{t('operations.noIncidents')}</td></tr>{/each}</tbody
      >
    </table>
  </div>
  <details>
    <summary>{t('operations.dockerLifecycleHistory')}</summary
    >{#each live?.events ?? [] as event (event.id)}<p class="muted">
        <time>{new Date(event.occurred_at).toLocaleString()}</time> · {event.service_name} · {event.event_type}{event.exit_code !==
        null
          ? ` · exit ${event.exit_code}`
          : ''}
      </p>{/each}
  </details>
</section>
