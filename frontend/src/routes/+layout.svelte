<script lang="ts">
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { browser } from '$app/environment';
  import { fade } from 'svelte/transition';
  import type { Snippet } from 'svelte';
  import MobileNav from '$lib/components/MobileNav.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import CursorGlow from '$lib/components/CursorGlow.svelte';
  import { NAV_ITEMS, isActiveNavItem } from '$lib/nav';

  let { children }: { children: Snippet } = $props();

  const reducedMotion = browser && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const transitionDuration = reducedMotion ? 0 : 180;
</script>

<CursorGlow />

<div class="min-h-screen md:grid md:grid-cols-[220px_1fr]">
  <MobileNav />
  <aside
    class="border-line bg-panel-alt hidden md:sticky md:top-0 md:flex md:h-screen md:flex-col md:overflow-y-auto md:border-r"
  >
    <div class="border-line flex h-[72px] items-center gap-3 border-b px-5">
      <span
        class="border-brand text-brand neon-glow grid size-9 shrink-0 place-items-center rounded-xl border font-mono text-[11px] font-bold"
        >AW</span
      >
      <div class="min-w-0">
        <strong class="text-heading block truncate text-sm">Engineering Worker</strong><small
          class="text-muted block text-[10px] tracking-widest uppercase">Control center</small
        >
      </div>
    </div>
    <nav class="flex-1 space-y-1 p-3">
      {#each NAV_ITEMS as item (item.href)}
        <a
          href={resolve(item.href)}
          class="block rounded-lg border-l-2 px-3 py-2.5 text-sm transition-all duration-200 ease-smooth hover:translate-x-0.5 {isActiveNavItem(
            page.url.pathname,
            item.href
          )
            ? 'border-brand bg-panel text-heading'
            : 'text-muted hover:text-heading border-transparent'}">{item.label}</a
        >
      {/each}
    </nav>
    <div class="border-line flex items-center justify-between border-t px-4 py-3">
      <span class="text-muted text-xs">Theme</span>
      <ThemeToggle />
    </div>
  </aside>
  <div class="min-w-0">
    {#key page.url.pathname}
      <div in:fade={{ duration: transitionDuration }}>
        {@render children()}
      </div>
    {/key}
  </div>
</div>
