<script lang="ts">
  import EChart from './EChart.svelte';
  import { chartColors } from './chart-colors.svelte';
  import { t } from '$lib/i18n/index.svelte';
  let {
    label,
    value,
    warning = 85
  }: { label: string; value: number | null; warning?: number } = $props();
  const display = $derived(value === null ? t('operations.unavailable') : `${value.toFixed(1)}%`);
  const hot = $derived(value !== null && value >= warning);
</script>

<article class:hot>
  <h3>{label}</h3>
  {#if value !== null}
    {@const colors = chartColors()}
    <EChart
      height={180}
      summary={`${label}: ${display}`}
      option={{
        series: [
          {
            type: 'gauge',
            min: 0,
            max: 100,
            startAngle: 210,
            endAngle: -30,
            radius: '95%',
            progress: { show: true, width: 10, itemStyle: { shadowBlur: 12 } },
            axisLine: {
              lineStyle: {
                width: 10,
                color: [
                  [warning / 100, colors.line],
                  [1, colors.warning]
                ]
              }
            },
            axisTick: { show: false },
            splitLine: { length: 8 },
            axisLabel: { distance: 16, fontSize: 10 },
            detail: {
              valueAnimation: true,
              formatter: '{value}%',
              fontSize: 23,
              offsetCenter: [0, '55%'],
              color: 'inherit'
            },
            data: [{ value: Number(value.toFixed(1)) }],
            itemStyle: {
              color: hot ? colors.warning : colors.brand2,
              shadowColor: hot ? colors.warning : colors.brand2,
              shadowBlur: 14
            }
          }
        ]
      }}
    />
  {:else}<p class="empty">
      {t('operations.unavailable')}<span>{t('operations.noCurrentMeasurement')}</span>
    </p>{/if}
</article>

<style>
  article {
    padding: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    min-width: 0;
    background: var(--color-panel);
    position: relative;
    overflow: hidden;
    transition:
      border-color 0.3s var(--ease-smooth),
      box-shadow 0.3s var(--ease-smooth);
  }
  article::before {
    content: '';
    position: absolute;
    inset: -30% -30% auto -30%;
    height: 60%;
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--color-brand-2) 20%, transparent),
      transparent 70%
    );
    pointer-events: none;
    opacity: 0.6;
    transition: opacity 0.3s var(--ease-smooth);
  }
  article.hot::before {
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--color-warning) 22%, transparent),
      transparent 70%
    );
  }
  article:hover {
    border-color: color-mix(in srgb, var(--color-brand-2) 50%, var(--color-line));
    box-shadow: 0 0 20px -6px color-mix(in srgb, var(--color-brand-2) 40%, transparent);
  }
  article:hover::before {
    opacity: 1;
  }
  article.hot:hover {
    border-color: color-mix(in srgb, var(--color-warning) 55%, var(--color-line));
    box-shadow: 0 0 20px -6px color-mix(in srgb, var(--color-warning) 45%, transparent);
  }
  h3 {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-muted);
  }
  .empty {
    min-height: 180px;
    display: grid;
    place-content: center;
    text-align: center;
    font-size: 1.3rem;
  }
  span {
    font-size: 0.8rem;
    opacity: 0.6;
  }
</style>
