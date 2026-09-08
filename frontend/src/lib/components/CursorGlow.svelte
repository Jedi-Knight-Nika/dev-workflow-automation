<script lang="ts">
  import { onMount } from 'svelte';

  let x = $state(-100);
  let y = $state(-100);
  let visible = $state(false);
  let active = $state(false);
  type Trail = { id: number; x: number; y: number; size: number };
  let trail = $state<Trail[]>([]);
  let nextId = 0;
  let lastX = -100;
  let lastY = -100;
  let lastTrailAt = 0;

  const TRAIL_LIFETIME_MS = 760;
  const MAX_TRAIL_POINTS = 12;

  onMount(() => {
    const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (isCoarsePointer || reducedMotion) return;

    active = true;

    function handleMove(event: PointerEvent) {
      x = event.clientX;
      y = event.clientY;
      visible = true;

      const now = performance.now();
      const distance = Math.hypot(event.clientX - lastX, event.clientY - lastY);
      if (distance < 9 || now - lastTrailAt < 28) return;

      lastX = event.clientX;
      lastY = event.clientY;
      lastTrailAt = now;
      const id = nextId++;
      trail = [
        ...trail,
        { id, x: event.clientX, y: event.clientY, size: 24 + Math.min(distance, 28) }
      ].slice(-MAX_TRAIL_POINTS);
      window.setTimeout(() => {
        trail = trail.filter((point) => point.id !== id);
      }, TRAIL_LIFETIME_MS);
    }
    function handleLeave() {
      visible = false;
    }

    window.addEventListener('pointermove', handleMove, { passive: true });
    document.documentElement.addEventListener('mouseleave', handleLeave);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      document.documentElement.removeEventListener('mouseleave', handleLeave);
    };
  });
</script>

{#if active}
  {#each trail as point (point.id)}
    <div
      class="pointer-events-none fixed top-0 left-0 z-[9997]"
      style="
        transform: translate3d({point.x - point.size / 2}px, {point.y - point.size * 0.36}px, 0);
      "
    >
      <span
        class="block rounded-full"
        style="
          width: {point.size}px;
          height: {point.size * 0.72}px;
          background: radial-gradient(ellipse, color-mix(in srgb, var(--color-brand) 34%, transparent) 0%, color-mix(in srgb, var(--color-brand-2) 15%, transparent) 42%, transparent 72%);
          filter: blur(5px);
          animation: cursor-smoke {TRAIL_LIFETIME_MS}ms cubic-bezier(0.16, 0.72, 0.24, 1) forwards;
        "
      ></span>
    </div>
  {/each}
  <div
    class="pointer-events-none fixed top-0 left-0 z-[9999] size-8 rounded-full"
    style="
      transform: translate3d({x - 16}px, {y - 16}px, 0);
      opacity: {visible ? 1 : 0};
      background: radial-gradient(circle, color-mix(in srgb, var(--color-brand) 52%, transparent) 0%, color-mix(in srgb, var(--color-brand-2) 16%, transparent) 42%, transparent 72%);
      filter: blur(1px);
      transition: transform 0.1s var(--ease-smooth), opacity 0.3s ease;
      mix-blend-mode: screen;
    "
  ></div>
{/if}

<style>
  @keyframes -global-cursor-smoke {
    0% {
      opacity: 0.58;
      transform: scale(0.55);
    }
    65% {
      opacity: 0.2;
    }
    100% {
      opacity: 0;
      transform: scale(1.75);
    }
  }
</style>
