<script lang="ts">
  import { onMount } from 'svelte';
  import type { ECharts, EChartsOption } from 'echarts';
  import { chartColors, categoricalPalette } from './chart-colors.svelte';
  let {
    option,
    summary,
    height = 240
  }: { option: EChartsOption; summary: string; height?: number } = $props();
  let element: HTMLDivElement;
  let chart = $state<ECharts | null>(null);
  let reduce = $state(false);
  let textColor = $state('#94a3b8');
  let error = $state('');
  $effect(() => {
    const colors = chartColors();
    const tooltip = {
      backgroundColor: `color-mix(in srgb, ${colors.brand2} 6%, black 82%)`,
      borderColor: colors.brand2,
      borderWidth: 1,
      extraCssText: `backdrop-filter: blur(6px); box-shadow: 0 0 18px color-mix(in srgb, ${colors.brand2} 35%, transparent);`,
      textStyle: { color: '#f1eefb' },
      ...(option.tooltip ?? {})
    };
    chart?.setOption(
      {
        color: categoricalPalette(),
        ...option,
        tooltip,
        animation: !reduce,
        textStyle: { color: textColor }
      },
      { notMerge: true }
    );
  });
  onMount(() => {
    let disposed = false;
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => {
      reduce = motion.matches;
      textColor = getComputedStyle(element).color;
    };
    update();
    motion.addEventListener('change', update);
    const resize = new ResizeObserver(() => chart?.resize());
    resize.observe(element);
    const theme = new MutationObserver(update);
    theme.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-theme']
    });
    void import('./chart-runtime')
      .then(({ init }) => {
        if (!disposed) chart = init(element) as unknown as ECharts;
      })
      .catch(() => {
        if (!disposed) error = 'Chart unavailable';
      });
    return () => {
      disposed = true;
      motion.removeEventListener('change', update);
      resize.disconnect();
      theme.disconnect();
      chart?.dispose();
      chart = null;
    };
  });
</script>

<figure>
  <div bind:this={element} style:height="{height}px" aria-hidden="true"></div>
  <figcaption>
    {summary}{#if error}
      · {error}{/if}
  </figcaption>
</figure>

<style>
  figure {
    margin: 0;
    min-width: 0;
  }
  figcaption {
    font-size: 0.8rem;
    color: var(--color-muted, #94a3b8);
  }
</style>
