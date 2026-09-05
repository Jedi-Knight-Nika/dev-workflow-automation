<script lang="ts">
  import { onMount } from 'svelte';

  let x = $state(-100);
  let y = $state(-100);
  let visible = $state(false);
  let active = $state(false);

  onMount(() => {
    const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (isCoarsePointer || reducedMotion) return;

    active = true;

    function handleMove(event: PointerEvent) {
      x = event.clientX;
      y = event.clientY;
      visible = true;
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
  <div
    class="pointer-events-none fixed top-0 left-0 z-[9999] size-9 rounded-full"
    style="
      transform: translate3d({x - 18}px, {y - 18}px, 0);
      opacity: {visible ? 1 : 0};
      background: radial-gradient(circle, color-mix(in srgb, var(--color-brand) 45%, transparent) 0%, transparent 72%);
      transition: transform 0.15s var(--ease-smooth), opacity 0.4s ease;
      mix-blend-mode: screen;
    "
  ></div>
{/if}
