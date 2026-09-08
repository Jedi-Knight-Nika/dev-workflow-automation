<script lang="ts">
  import type { CostForecast, ForecastAccuracy } from '$lib/types/analytics';
  import { bytes, count, duration, money, percent } from './format';
  import './analytics-panels.css';
  let {
    forecasts,
    accuracy
  }: { forecasts: (CostForecast | null)[]; accuracy: ForecastAccuracy | null } = $props();
</script>

<section class="ops-panel">
  <h3>Forecasts · advisory</h3>
  <div class="cards">
    {#each forecasts as forecast, index (index)}<article>
        <small
          >{index === 0 ? 'Queued work' : `${index === 1 ? 7 : 30}-day spending scenario`}</small
        ><strong>{money(forecast?.estimate)}</strong><span
          >P90 {money(forecast?.range?.p90)} · {forecast?.confidence ?? 'UNAVAILABLE'} · n={forecast?.sample_count ??
            0}</span
        >{#if index === 0}<span
            >Active time {duration(forecast?.metrics?.developer_active_seconds?.estimate)} · Drain {duration(
              forecast?.queue_drain_seconds
            )}</span
          ><span>Concurrent RAM P90 {bytes(forecast?.predicted_peak_concurrent_memory_bytes)}</span
          >{/if}<span
          >Input / output {count(forecast?.metrics?.input_tokens?.estimate)} / {count(
            forecast?.metrics?.output_tokens?.estimate
          )}</span
        >{#if index > 0}<span
            >Tasks {count(forecast?.metrics?.task_volume?.estimate)} · Developer hours {count(
              forecast?.metrics?.developer_compute_hours?.estimate
            )}</span
          >{/if}<small>{forecast?.basis}</small>
      </article>{/each}
  </div>
  <details>
    <summary>Forecast accuracy</summary>
    <div class="scroll">
      <table>
        <thead
          ><tr
            ><th>Metric</th><th>Samples</th><th>Median absolute % error</th><th>P90 coverage</th><th
              >Mean bias</th
            ></tr
          ></thead
        ><tbody
          >{#each Object.entries(accuracy?.metrics ?? {}) as [key, value] (key)}<tr
              ><td>{key.replaceAll('_', ' ')}</td><td>{value.sample_count}</td><td
                >{percent(value.median_absolute_percentage_error)}</td
              ><td>{percent(value.p90_coverage)}</td><td
                >{value.mean_bias?.toFixed(2) ?? 'Unavailable'}</td
              ></tr
            >{/each}</tbody
        >
      </table>
    </div>
    <p class="muted">{accuracy?.basis ?? 'No finalized forecast evidence yet.'}</p>
  </details>
</section>
