<script lang="ts">
  import { onMount } from 'svelte';

  type Particle = { angle: number; distance: number };
  type Burst = { id: number; x: number; y: number; color: string; particles: Particle[] };

  let bursts = $state<Burst[]>([]);
  let nextId = 0;
  const MAX_BURSTS = 6;
  const PARTICLE_COUNT = 6;
  const LIFETIME_MS = 650;

  onMount(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    function handleClick(event: MouseEvent) {
      const color = Math.random() > 0.5 ? 'var(--color-brand)' : 'var(--color-brand-2)';
      const particles: Particle[] = Array.from({ length: PARTICLE_COUNT }, (_, index) => ({
        angle: (360 / PARTICLE_COUNT) * index + (Math.random() * 26 - 13),
        distance: 22 + Math.random() * 18
      }));
      const id = nextId++;
      bursts = [...bursts, { id, x: event.clientX, y: event.clientY, color, particles }].slice(
        -MAX_BURSTS
      );
      setTimeout(() => {
        bursts = bursts.filter((burst) => burst.id !== id);
      }, LIFETIME_MS);
    }

    window.addEventListener('click', handleClick, { passive: true });
    return () => window.removeEventListener('click', handleClick);
  });
</script>

{#each bursts as burst (burst.id)}
  <div
    class="pointer-events-none fixed top-0 left-0 z-[9998]"
    style="transform: translate3d({burst.x}px, {burst.y}px, 0);"
  >
    <span
      class="absolute rounded-full"
      style="
        width: 10px; height: 10px; margin: -5px 0 0 -5px; border: 1px solid {burst.color};
        animation: click-ring {LIFETIME_MS}ms ease-out forwards;
      "
    ></span>
    {#each burst.particles as particle (particle.angle)}
      <span
        class="absolute rounded-full"
        style="
          width: 4px; height: 4px; margin: -2px 0 0 -2px; background: {burst.color};
          --angle: {particle.angle}deg; --distance: {particle.distance}px;
          animation: click-particle {LIFETIME_MS}ms ease-out forwards;
        "
      ></span>
    {/each}
  </div>
{/each}

<style>
  @keyframes -global-click-ring {
    0% {
      transform: scale(0.3);
      opacity: 0.8;
    }
    100% {
      transform: scale(3.2);
      opacity: 0;
    }
  }

  @keyframes -global-click-particle {
    0% {
      transform: rotate(var(--angle)) translateX(0) rotate(calc(var(--angle) * -1));
      opacity: 1;
    }
    100% {
      transform: rotate(var(--angle)) translateX(var(--distance)) rotate(calc(var(--angle) * -1));
      opacity: 0;
    }
  }
</style>
