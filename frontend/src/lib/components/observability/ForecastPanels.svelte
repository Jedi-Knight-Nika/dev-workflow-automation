<script lang="ts">
  import type { CostForecast, ForecastAccuracy } from '$lib/types/analytics';
  import { bytes, count, duration, money, percent } from './format';
  import { t } from '$lib/i18n/index.svelte';
  import './analytics-panels.css';
  let {
    forecasts,
    accuracy
  }: { forecasts: (CostForecast | null)[]; accuracy: ForecastAccuracy | null } = $props();
</script>

<section class="ops-panel">
  <h3>{t('operations.forecastsAdvisory')}</h3>
  <div class="cards">
    {#each forecasts as forecast, index (index)}<article>
        <small
          >{index === 0
            ? t('operations.queuedWork')
            : t('operations.spendingScenario', { days: index === 1 ? 7 : 30 })}</small
        ><strong>{money(forecast?.estimate)}</strong><span
          >{t('operations.p90Confidence', {
            p90: money(forecast?.range?.p90),
            confidence: forecast?.confidence ?? t('operations.unavailable'),
            count: forecast?.sample_count ?? 0
          })}</span
        >{#if index === 0}<span
            >{t('operations.activeTimeDrain', {
              active: duration(forecast?.metrics?.developer_active_seconds?.estimate),
              drain: duration(forecast?.queue_drain_seconds)
            })}</span
          ><span
            >{t('operations.concurrentRamP90', {
              value: bytes(forecast?.predicted_peak_concurrent_memory_bytes)
            })}</span
          >{/if}<span
          >{t('operations.inputOutput')}
          {count(forecast?.metrics?.input_tokens?.estimate)} / {count(
            forecast?.metrics?.output_tokens?.estimate
          )}</span
        >{#if index > 0}<span
            >{t('operations.tasksDeveloperHours', {
              tasks: count(forecast?.metrics?.task_volume?.estimate),
              hours: count(forecast?.metrics?.developer_compute_hours?.estimate)
            })}</span
          >{/if}<small>{forecast?.basis}</small>
      </article>{/each}
  </div>
  <details>
    <summary>{t('operations.forecastAccuracy')}</summary>
    <div class="scroll">
      <table>
        <thead
          ><tr
            ><th>{t('operations.colMetric')}</th><th>{t('operations.colSamples')}</th><th
              >{t('operations.colMedianError')}</th
            ><th>{t('operations.colP90Coverage')}</th><th>{t('operations.colMeanBias')}</th></tr
          ></thead
        ><tbody
          >{#each Object.entries(accuracy?.metrics ?? {}) as [key, value] (key)}<tr
              ><td>{key.replaceAll('_', ' ')}</td><td>{value.sample_count}</td><td
                >{percent(value.median_absolute_percentage_error)}</td
              ><td>{percent(value.p90_coverage)}</td><td
                >{value.mean_bias?.toFixed(2) ?? t('operations.unavailable')}</td
              ></tr
            >{/each}</tbody
        >
      </table>
    </div>
    <p class="muted">{accuracy?.basis ?? t('operations.noForecastEvidence')}</p>
  </details>
</section>
