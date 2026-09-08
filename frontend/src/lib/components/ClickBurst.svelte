<script lang="ts">
  import { onMount } from 'svelte';
  import { getDisplayMode } from '$lib/display.svelte';

  type Burst = { id: number; x: number; y: number; color: string };

  let bursts = $state<Burst[]>([]);
  let nextId = 0;
  const MAX_BURSTS = 6;
  const LIFETIME_MS = 720;
  const JARVIS_LIFETIME_MS = 520;

  const jarvis = $derived(getDisplayMode() === 'jarvis');

  onMount(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    function handlePointerDown(event: PointerEvent) {
      if (event.button !== 0) return;
      const color = Math.random() > 0.5 ? 'var(--color-brand)' : 'var(--color-brand-2)';
      const id = nextId++;
      bursts = [...bursts, { id, x: event.clientX, y: event.clientY, color }].slice(-MAX_BURSTS);
      const lifetime = getDisplayMode() === 'jarvis' ? JARVIS_LIFETIME_MS : LIFETIME_MS;
      setTimeout(() => {
        bursts = bursts.filter((burst) => burst.id !== id);
      }, lifetime);
    }

    window.addEventListener('pointerdown', handlePointerDown, { passive: true });
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  });
</script>

{#each bursts as burst (burst.id)}
  <div
    class="pointer-events-none fixed top-0 left-0 z-[9998]"
    style="transform: translate3d({burst.x}px, {burst.y}px, 0);"
  >
    {#if jarvis}
      <span
        class="absolute lock"
        style="--rc: {burst.color}; animation-duration: {JARVIS_LIFETIME_MS}ms;"
      ></span>
      <span
        class="absolute lock-dot"
        style="--rc: {burst.color}; animation-duration: {JARVIS_LIFETIME_MS}ms;"
      ></span>
    {:else}
      <span
        class="absolute rounded-full click-bloom"
        style="
        width: 18px; height: 18px; margin: -9px 0 0 -9px;
        background: radial-gradient(circle, color-mix(in srgb, {burst.color} 60%, transparent), transparent 70%);
        animation: click-bloom {LIFETIME_MS}ms ease-out forwards;
      "
      ></span>
      <span
        class="absolute rounded-full"
        style="width: 12px; height: 12px; margin: -6px 0 0 -6px; border: 1px solid {burst.color}; animation: click-ring {LIFETIME_MS}ms cubic-bezier(0.16, 0.72, 0.24, 1) forwards;"
      ></span>
      <span
        class="absolute rounded-full"
        style="width: 12px; height: 12px; margin: -6px 0 0 -6px; border: 1px solid color-mix(in srgb, {burst.color} 55%, transparent); animation: click-ring-soft {LIFETIME_MS}ms cubic-bezier(0.16, 0.72, 0.24, 1) forwards;"
      ></span>
    {/if}
  </div>
{/each}

<style>
  @keyframes -global-click-ring {
    0% {
      transform: scale(0.35);
      opacity: 0.9;
    }
    100% {
      transform: scale(4.5);
      opacity: 0;
    }
  }

  @keyframes -global-click-ring-soft {
    0% {
      transform: scale(0.45);
      opacity: 0;
    }
    22% {
      opacity: 0.45;
    }
    100% {
      transform: scale(7);
      opacity: 0;
    }
  }

  @keyframes -global-click-bloom {
    0% {
      transform: scale(0.35);
      opacity: 0.85;
      filter: blur(1px);
    }
    100% {
      transform: scale(3.8);
      opacity: 0;
      filter: blur(8px);
    }
  }

  .lock {
    top: -10px;
    left: -10px;
    width: 20px;
    height: 20px;
    border: 1.5px solid var(--rc);
    box-shadow: 0 0 8px 1px color-mix(in srgb, var(--rc) 55%, transparent);
    animation-name: -global-jarvis-click-lock;
    animation-timing-function: cubic-bezier(0.16, 0.84, 0.3, 1);
    animation-fill-mode: forwards;
  }
  .lock-dot {
    top: -1.5px;
    left: -1.5px;
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: var(--rc);
    box-shadow: 0 0 6px 1px color-mix(in srgb, var(--rc) 70%, transparent);
    animation-name: -global-jarvis-click-dot;
    animation-timing-function: ease-out;
    animation-fill-mode: forwards;
  }
  @keyframes -global-jarvis-click-lock {
    0% {
      transform: scale(1.9);
      opacity: 0;
    }
    30% {
      opacity: 1;
    }
    100% {
      transform: scale(1);
      opacity: 0;
    }
  }
  @keyframes -global-jarvis-click-dot {
    0% {
      opacity: 1;
    }
    100% {
      opacity: 0;
    }
  }
</style>
