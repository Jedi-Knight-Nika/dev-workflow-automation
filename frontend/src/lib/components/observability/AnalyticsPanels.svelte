<script lang="ts">
  import type { AnalyticsDashboard } from '$lib/types/analytics';
  import type { EChartsOption } from 'echarts';
  import EChart from './EChart.svelte';
  import { chartColors, hexAlpha } from './chart-colors.svelte';
  import { count, duration, money, percent } from './format';
  import './analytics-panels.css';
  let { analytics, days }: { analytics: AnalyticsDashboard; days: number } = $props();
  function comparison(
    rows: { key: string; known_cost_usd: string }[],
    names: Record<string, string> = {}
  ): EChartsOption {
    const colors = chartColors();
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 55, right: 15, bottom: 80 },
      xAxis: {
        type: 'category',
        data: rows.map((r) => names[r.key] || r.key),
        axisLabel: { rotate: 20, width: 110, overflow: 'truncate' }
      },
      yAxis: { type: 'value', name: 'USD' },
      series: [
        {
          type: 'bar',
          data: rows.map((r) => Number(r.known_cost_usd)),
          itemStyle: {
            color: colors.brand2,
            shadowColor: colors.brand2,
            shadowBlur: 8,
            borderRadius: [4, 4, 0, 0]
          }
        }
      ]
    };
  }
</script>

<section class="ops-panel">
  <h3>AI cost & efficiency</h3>
  <div class="cards">
    {#each [1, 7, 30] as window (window)}<article>
        <small>Known AI cost · {window === 1 ? '24 hours' : `${window} days`}</small><strong
          >{money(analytics.period_costs?.[window]?.known_cost_usd)}</strong
        ><span>{analytics.period_costs?.[window]?.unknown_cost_runs ?? 0} unknown-cost runs</span>
      </article>{/each}
    <article>
      <small>Input / output · {days}d</small><strong
        >{count(analytics.totals.input_tokens)} / {count(analytics.totals.output_tokens)}</strong
      ><span
        >Cached subset {count(analytics.totals.cache_read_tokens)} · Cache writes {count(
          analytics.totals.cache_write_tokens
        )} · Reasoning subset {count(analytics.totals.reasoning_tokens)}</span
      >
    </article>
    <article>
      <small>Cost per merged task</small><strong>{money(analytics.cost_per_merged_task_usd)}</strong
      ><span
        >{analytics.complete_merged_tasks} complete · {analytics.excluded_incomplete_tasks} excluded</span
      >
    </article>
    <article>
      <small>Failed / compaction spend</small><strong
        >{money(analytics.totals.failed_spend_usd)} / {money(
          analytics.totals.compaction_spend_usd
        )}</strong
      ><span>Reserved {money(analytics.totals.reserved_usd)}</span>
    </article>
  </div>
  <div class="charts">
    <EChart
      summary={`Daily AI cost · ${days}d · UTC. Incomplete costs remain gaps.`}
      option={{
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: analytics.daily.map((d) => d.key) },
        yAxis: { type: 'value', name: 'USD' },
        series: [
          {
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            lineStyle: { width: 2.5, shadowBlur: 10, shadowColor: chartColors().brand2 },
            areaStyle: {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: hexAlpha(chartColors().brand2, 0.32) },
                  { offset: 1, color: hexAlpha(chartColors().brand2, 0) }
                ]
              }
            },
            data: analytics.daily.map((d) => (d.cost_complete ? Number(d.cost_usd) : null)),
            connectNulls: false
          }
        ]
      }}
    />
    <EChart
      summary="Input and output tokens by model. Cached input and reasoning are subsets."
      option={{
        tooltip: { trigger: 'axis' },
        legend: { data: ['Input', 'Output'] },
        grid: { left: 65, right: 15, bottom: 80 },
        xAxis: {
          type: 'category',
          data: analytics.models.map((m) => m.key),
          axisLabel: { rotate: 20, width: 110, overflow: 'truncate' }
        },
        yAxis: { type: 'value' },
        series: [
          {
            name: 'Input',
            type: 'bar',
            stack: 'tokens',
            data: analytics.models.map((m) => m.input_tokens)
          },
          {
            name: 'Output',
            type: 'bar',
            stack: 'tokens',
            data: analytics.models.map((m) => m.output_tokens)
          }
        ]
      }}
    />
  </div>
  <details>
    <summary>Cost by model, agent, repository & run kind</summary>
    <div class="charts">
      <EChart summary="Known cost by model" option={comparison(analytics.models)} /><EChart
        summary="Known cost by agent"
        option={comparison(
          analytics.agents,
          Object.fromEntries(analytics.agents.map((a) => [a.key, a.display_name]))
        )}
      /><EChart
        summary="Known cost by repository"
        option={comparison(analytics.repositories, analytics.repository_names)}
      /><EChart summary="Known cost by run kind" option={comparison(analytics.run_kinds)} />
    </div>
  </details>
  <h3>Agent leaderboard</h3>
  <div class="scroll">
    <table>
      <thead
        ><tr
          ><th>Profile / Team</th><th>Harness / model</th><th>Merged / terminal</th><th>Success</th
          ><th>Median / P90 cost</th><th>Median / P90 active</th><th>Tokens / merged</th><th
            >Fixes / task</th
          ><th>Human intervention</th></tr
        ></thead
      ><tbody
        >{#each analytics.agents as a (a.key)}<tr
            ><td>{a.display_name || a.key}<small>{a.teams?.join(', ')}</small></td><td
              >{a.harnesses.join(', ')}<small>{a.models.join(', ')}</small></td
            ><td>{a.tasks_merged} / {a.terminal_tasks}</td><td>{percent(a.success_rate)}</td><td
              >{money(a.median_cost_usd)} / {money(a.p90_cost_usd)}</td
            ><td>{duration(a.median_developer_seconds)} / {duration(a.p90_developer_seconds)}</td
            ><td>{count(a.tokens_per_merged_task)}</td><td
              >{a.review_fix_cycles_per_task?.toFixed(1) ?? 'Unknown'}</td
            ><td>{percent(a.human_intervention_rate)}</td></tr
          >{:else}<tr><td colspan="9">No agent receipts in this window.</td></tr>{/each}</tbody
      >
    </table>
  </div>
  <p class="muted">{analytics.basis}</p>
  <p class="muted">
    Provider failures {analytics.reliability?.provider_failures ?? 0} · Rate-limit failures {analytics
      .reliability?.rate_limit_failures ?? 0} · Validation failures {analytics.reliability
      ?.validation_failures ?? 0}
  </p>
  <details>
    <summary>Local Interpreter activity ({analytics.local_runs?.length ?? 0})</summary>
    <div class="scroll">
      <table>
        <thead><tr><th>Model</th><th>Status</th><th>Input / output</th><th>Duration</th></tr></thead
        ><tbody
          >{#each analytics.local_runs ?? [] as run, index (index)}<tr
              ><td>{run.model}</td><td>{run.status}</td><td
                >{count(run.input_tokens)} / {count(run.output_tokens)}</td
              ><td>{duration(run.duration_ms === null ? null : run.duration_ms / 1000)}</td></tr
            >{/each}</tbody
        >
      </table>
    </div>
  </details>
</section>
