<script lang="ts">
  import { onMount } from 'svelte';
  import { createHalo } from './halo';
  import type { OrbMode } from './types';
  import type { DisplayMode } from '$lib/display.svelte';
  let {
    mode = 'idle',
    size = 76,
    displayMode = 'default'
  }: { mode?: OrbMode; size?: number; displayMode?: DisplayMode } = $props();
  let canvas: HTMLCanvasElement;
  let ready = $state(false);
  let renderer = $state<ReturnType<typeof createHalo>>();
  $effect(() => {
    if (mode && displayMode) renderer?.refresh();
  });
  onMount(() => {
    try {
      if (!canvas.getContext('2d')) return;
      renderer = createHalo(
        canvas,
        () => mode,
        () => displayMode
      );
      ready = true;
      return () => renderer?.destroy();
    } catch {
      ready = false;
    }
  });
</script>

<span
  class="orb"
  style:width="{size}px"
  style:height="{size}px"
  data-mode={mode}
  data-display={displayMode}
  aria-hidden="true"
>
  <canvas bind:this={canvas} class:ready></canvas>
  {#if !ready}<svg viewBox="0 0 100 100"
      ><circle
        cx="50"
        cy="50"
        r="32"
        fill="none"
        stroke="currentColor"
        stroke-width="1"
        stroke-dasharray="1 3"
      /><ellipse
        cx="50"
        cy="50"
        rx="35"
        ry="27"
        fill="none"
        stroke="currentColor"
        opacity=".4"
      /><circle cx="50" cy="50" r="4" fill="currentColor" /></svg
    >{/if}
</span>

<style>
  .orb {
    display: inline-grid;
    place-items: center;
    position: relative;
    color: var(--color-brand-2, #65e5d4);
    flex-shrink: 0;
  }
  canvas,
  svg {
    position: absolute;
    width: 100%;
    height: 100%;
  }
  canvas {
    opacity: 0;
  }
  canvas.ready {
    opacity: 1;
  }
  [data-display='default'] svg circle:first-child {
    stroke-dasharray: none;
    stroke-width: 2;
  }
  [data-display='default'] svg ellipse {
    display: none;
  }
  [data-mode='critical'] {
    color: #fb7185;
  }
  [data-mode='warning'] {
    color: #fbbf24;
  }
</style>
