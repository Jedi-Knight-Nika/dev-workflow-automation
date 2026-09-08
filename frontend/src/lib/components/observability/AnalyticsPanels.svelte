<script lang="ts">
  import type { AnalyticsDashboard } from '$lib/types/analytics';
  import type { EChartsOption } from 'echarts';
  import EChart from './EChart.svelte';
  import { chartColors, hexAlpha } from './chart-colors.svelte';
  import { count, duration, money, percent } from './format';
  import { t } from '$lib/i18n/index.svelte';
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
  <h3>{t('operations.aiCostEfficiency')}</h3>
  <div class="cards">
    {#each [1, 7, 30] as window (window)}<article>
        <small
          >{t('operations.knownAiCost', {
            window:
              window === 1 ? t('operations.last24h') : t('operations.lastNDays', { count: window })
          })}</small
        ><strong>{money(analytics.period_costs?.[window]?.known_cost_usd)}</strong><span
          >{t('operations.unknownCostRuns', {
            count: analytics.period_costs?.[window]?.unknown_cost_runs ?? 0
          })}</span
        >
      </article>{/each}
    <article>
      <small>{t('operations.inputOutputWindow', { days })}</small><strong
        >{count(analytics.totals.input_tokens)} / {count(analytics.totals.output_tokens)}</strong
      ><span
        >{t('operations.cacheDetail', {
          cached: count(analytics.totals.cache_read_tokens),
          writes: count(analytics.totals.cache_write_tokens),
          reasoning: count(analytics.totals.reasoning_tokens)
        })}</span
      >
    </article>
    <article>
      <small>{t('operations.costPerMergedTask')}</small><strong
        >{money(analytics.cost_per_merged_task_usd)}</strong
      ><span
        >{t('operations.completeExcluded', {
          complete: analytics.complete_merged_tasks,
          excluded: analytics.excluded_incomplete_tasks
        })}</span
      >
    </article>
    <article>
      <small>{t('operations.failedCompactionSpend')}</small><strong
        >{money(analytics.totals.failed_spend_usd)} / {money(
          analytics.totals.compaction_spend_usd
        )}</strong
      ><span>{t('operations.reserved', { amount: money(analytics.totals.reserved_usd) })}</span>
    </article>
  </div>
  <div class="charts">
    <EChart
      summary={t('operations.dailyAiCost', { days })}
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
      summary={t('operations.tokensByModel')}
      option={{
        tooltip: { trigger: 'axis' },
        legend: { data: [t('operations.legendInput'), t('operations.legendOutput')] },
        grid: { left: 65, right: 15, bottom: 80 },
        xAxis: {
          type: 'category',
          data: analytics.models.map((m) => m.key),
          axisLabel: { rotate: 20, width: 110, overflow: 'truncate' }
        },
        yAxis: { type: 'value' },
        series: [
          {
            name: t('operations.legendInput'),
            type: 'bar',
            stack: 'tokens',
            data: analytics.models.map((m) => m.input_tokens)
          },
          {
            name: t('operations.legendOutput'),
            type: 'bar',
            stack: 'tokens',
            data: analytics.models.map((m) => m.output_tokens)
          }
        ]
      }}
    />
  </div>
  <details>
    <summary>{t('operations.costBreakdown')}</summary>
    <div class="charts">
      <EChart summary={t('operations.costByModel')} option={comparison(analytics.models)} /><EChart
        summary={t('operations.costByAgent')}
        option={comparison(
          analytics.agents,
          Object.fromEntries(analytics.agents.map((a) => [a.key, a.display_name]))
        )}
      /><EChart
        summary={t('operations.costByRepository')}
        option={comparison(analytics.repositories, analytics.repository_names)}
      /><EChart summary={t('operations.costByRunKind')} option={comparison(analytics.run_kinds)} />
    </div>
  </details>
  <h3>{t('operations.agentLeaderboard')}</h3>
  <div class="scroll">
    <table>
      <thead
        ><tr
          ><th>{t('operations.colProfileTeam')}</th><th>{t('operations.colHarnessModel')}</th><th
            >{t('operations.colMergedTerminal')}</th
          ><th>{t('operations.colSuccess')}</th><th>{t('operations.colCostMedianP90')}</th><th
            >{t('operations.colActiveMedianP90')}</th
          ><th>{t('operations.colTokensPerMerged')}</th><th>{t('operations.colFixesPerTask')}</th
          ><th>{t('operations.colHumanIntervention')}</th></tr
        ></thead
      ><tbody
        >{#each analytics.agents as a (a.key)}<tr
            ><td>{a.display_name || a.key}<small>{a.teams?.join(', ')}</small></td><td
              >{a.harnesses.join(', ')}<small>{a.models.join(', ')}</small></td
            ><td>{a.tasks_merged} / {a.terminal_tasks}</td><td>{percent(a.success_rate)}</td><td
              >{money(a.median_cost_usd)} / {money(a.p90_cost_usd)}</td
            ><td>{duration(a.median_developer_seconds)} / {duration(a.p90_developer_seconds)}</td
            ><td>{count(a.tokens_per_merged_task)}</td><td
              >{a.review_fix_cycles_per_task?.toFixed(1) ?? t('operations.unknownValue')}</td
            ><td>{percent(a.human_intervention_rate)}</td></tr
          >{:else}<tr><td colspan="9">{t('operations.noAgentReceipts')}</td></tr>{/each}</tbody
      >
    </table>
  </div>
  <p class="muted">{analytics.basis}</p>
  <p class="muted">
    {t('operations.reliabilityFailures', {
      provider: analytics.reliability?.provider_failures ?? 0,
      rateLimit: analytics.reliability?.rate_limit_failures ?? 0,
      validation: analytics.reliability?.validation_failures ?? 0
    })}
  </p>
  <details>
    <summary
      >{t('operations.localInterpreterActivity', {
        count: analytics.local_runs?.length ?? 0
      })}</summary
    >
    <div class="scroll">
      <table>
        <thead
          ><tr
            ><th>{t('operations.colModel')}</th><th>{t('operations.colStatus')}</th><th
              >{t('operations.inputOutput')}</th
            ><th>{t('operations.colDuration')}</th></tr
          ></thead
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
