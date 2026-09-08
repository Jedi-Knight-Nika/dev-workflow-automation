<script lang="ts">
  import type { TaskAnalytics, ForecastMetric } from '$lib/types/analytics';
  import { bytes, count, duration, money } from './format';
  import './analytics-panels.css';
  let { analytics }: { analytics: TaskAnalytics } = $props();
  function estimate(value: unknown): ForecastMetric {
    return value as ForecastMetric;
  }
  function display(key: string, value: unknown) {
    if (value === null || value === undefined) return 'Unavailable';
    const number = Number(value);
    return key.includes('cost')
      ? money(number)
      : key.includes('memory')
        ? bytes(number)
        : key.includes('seconds')
          ? duration(number)
          : count(number);
  }
</script>

<section class="ops-panel">
  <details>
    <summary>AI usage by run</summary>
    <div class="scroll">
      <table>
        <thead
          ><tr
            ><th>Run / model</th><th>Status</th><th>Input / output</th><th>Cache read / write</th
            ><th>Reasoning subset</th><th>Cost</th><th>Provider active / wall</th></tr
          ></thead
        ><tbody
          >{#each analytics.runs ?? [] as run (run.id)}<tr
              ><td>{run.run_kind}<small>{run.harness} · {run.model}</small></td><td>{run.status}</td
              ><td>{count(run.input_tokens)} / {count(run.output_tokens)}</td><td
                >{count(run.cache_read_tokens)} / {count(run.cache_write_tokens)}</td
              ><td>{count(run.reasoning_tokens)}</td><td>{money(run.cost)}</td><td
                >{duration(
                  run.provider_duration_ms === null ? null : run.provider_duration_ms / 1000
                )} / {duration(
                  run.finished_at
                    ? (Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000
                    : null
                )}</td
              ></tr
            >{:else}<tr><td colspan="7">No paid AI receipts recorded.</td></tr>{/each}</tbody
        >
      </table>
    </div>
  </details>
  <details>
    <summary>Wait reasons & phase timing</summary
    >{#each Object.entries(analytics.wait_seconds_by_reason ?? {}) as [reason, seconds] (reason)}<p>
        {reason.replaceAll('_', ' ')} · {duration(seconds)}
      </p>{/each}{#each Object.entries(analytics.phase_seconds ?? {}) as [phase, seconds] (phase)}<p
      >
        {phase.replaceAll('_', ' ')} · {duration(seconds)}
      </p>{/each}
    <p>
      Provider active {duration(analytics.provider_active_seconds)} · Provider wait {duration(
        analytics.provider_wait_seconds
      )} · First edit {duration(analytics.time_to_first_edit_seconds)}
    </p>
  </details>
  <details>
    <summary>Forecast vs actual</summary
    >{#each analytics.forecasts as forecast (forecast.forecast_version)}<p>
        {forecast.forecast_version} · {forecast.confidence} · n={forecast.sample_count}
      </p>
      <div class="scroll">
        <table>
          <thead><tr><th>Metric</th><th>P50</th><th>P90</th><th>Actual</th></tr></thead><tbody
            >{#each Object.entries(forecast.estimate) as [key, value] (key)}<tr
                ><td>{key.replaceAll('_', ' ')}</td><td
                  >{display(key, estimate(value)?.estimate)}</td
                ><td>{display(key, estimate(value)?.range?.p90)}</td><td
                  >{display(key, forecast.actuals?.[key])}</td
                ></tr
              >{/each}</tbody
          >
        </table>
      </div>{:else}<p>No pre-execution forecast recorded.</p>{/each}
  </details>
  <details>
    <summary>Local Interpreter calls</summary
    >{#each analytics.local_runs ?? [] as run, index (index)}<p>
        {run.model} · {run.status} · {count(run.input_tokens)} in / {count(run.output_tokens)} out · {duration(
          run.duration_ms === null ? null : run.duration_ms / 1000
        )}
      </p>{:else}<p>No local calls recorded.</p>{/each}
  </details>
</section>
