<script lang="ts">
  import EChart from './EChart.svelte';
  import { chartColors } from './chart-colors.svelte';
  import { t } from '$lib/i18n/index.svelte';
  let {
    label,
    value,
    warning = 85
  }: { label: string; value: number | null; warning?: number } = $props();
  const hot = $derived(value !== null && value >= warning);
  const colors = $derived(chartColors());
</script>

<EChart
  height={220}
  summary={`${label}: ${value === null ? t('operations.unavailable') : value.toFixed(1) + '%'}`}
  option={{
    series: [
      {
        type: 'gauge',
        startAngle: 90,
        endAngle: -270,
        radius: '80%',
        pointer: { show: false },
        progress: {
          show: true,
          roundCap: true,
          width: 14,
          itemStyle: {
            color: hot ? colors.warning : colors.brand2,
            shadowColor: hot ? colors.warning : colors.brand2,
            shadowBlur: 14
          }
        },
        axisLine: { lineStyle: { width: 14, color: [[1, colors.line]] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: {
          formatter: () => (value === null ? t('operations.unavailable') : value.toFixed(1) + '%'),
          fontSize: 24,
          offsetCenter: [0, 0]
        },
        title: { offsetCenter: [0, '45%'], fontSize: 13 },
        data: [{ value: value ?? 0, name: label }]
      }
    ]
  }}
/>
