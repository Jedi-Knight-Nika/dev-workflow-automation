<script lang="ts">
  import { onMount } from 'svelte';

  type Burst = { id: number; x: number; y: number; color: string };

  let bursts = $state<Burst[]>([]);
  let nextId = 0;
  const MAX_BURSTS = 6;
  const LIFETIME_MS = 720;

  onMount(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    function handlePointerDown(event: PointerEvent) {
      if (event.button !== 0) return;
      const color = Math.random() > 0.5 ? 'var(--color-brand)' : 'var(--color-brand-2)';
      const id = nextId++;
      bursts = [...bursts, { id, x: event.clientX, y: event.clientY, color }].slice(-MAX_BURSTS);
      setTimeout(() => {
        bursts = bursts.filter((burst) => burst.id !== id);
      }, LIFETIME_MS);
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
</style>
