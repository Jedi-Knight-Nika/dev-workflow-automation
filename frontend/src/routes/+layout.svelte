<script lang="ts">
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { browser } from '$app/environment';
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import type { Snippet } from 'svelte';
  import MobileNav from '$lib/components/MobileNav.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import LanguageToggle from '$lib/components/LanguageToggle.svelte';
  import CursorGlow from '$lib/components/CursorGlow.svelte';
  import ClickBurst from '$lib/components/ClickBurst.svelte';
  import NotificationCenter from '$lib/components/NotificationCenter.svelte';
  import { NAV_ITEMS, isActiveNavItem } from '$lib/nav';
  import { t } from '$lib/i18n/index.svelte';

  let { children }: { children: Snippet } = $props();

  const reducedMotion = browser && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const transitionDuration = reducedMotion ? 0 : 180;

  const SIDEBAR_STORAGE_KEY = 'sidebarWidth';
  const MIN_SIDEBAR_WIDTH = 180;
  const MAX_SIDEBAR_WIDTH = 360;
  const DEFAULT_SIDEBAR_WIDTH = 220;

  let sidebarWidth = $state(DEFAULT_SIDEBAR_WIDTH);
  let resizing = $state(false);

  onMount(() => {
    try {
      const stored = Number(localStorage.getItem(SIDEBAR_STORAGE_KEY));
      if (stored >= MIN_SIDEBAR_WIDTH && stored <= MAX_SIDEBAR_WIDTH) {
        sidebarWidth = stored;
      }
    } catch {
      /* storage unavailable */
    }
  });

  function startResize(event: PointerEvent) {
    event.preventDefault();
    resizing = true;
    const startX = event.clientX;
    const startWidth = sidebarWidth;

    function handleMove(moveEvent: PointerEvent) {
      const next = startWidth + (moveEvent.clientX - startX);
      sidebarWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, next));
    }
    function handleUp() {
      resizing = false;
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarWidth));
      } catch {
        /* storage unavailable */
      }
    }
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
  }
</script>

<CursorGlow />
<ClickBurst />
<NotificationCenter />

<div class="min-h-screen md:grid" style="grid-template-columns: {sidebarWidth}px 1fr">
  <MobileNav />
  <aside
    class="border-line bg-panel-alt/80 relative hidden backdrop-blur-md bg-[radial-gradient(circle_at_0%_0%,color-mix(in_srgb,var(--color-brand)_14%,transparent),transparent_45%),radial-gradient(circle_at_100%_100%,color-mix(in_srgb,var(--color-brand-2)_10%,transparent),transparent_50%)] md:sticky md:top-0 md:flex md:h-screen md:flex-col md:overflow-y-auto md:border-r"
  >
    <div class="border-line flex h-[72px] items-center border-b px-5">
      <a
        href={resolve('/')}
        class="flex min-w-0 items-center gap-3 rounded-lg transition-opacity hover:opacity-80"
      >
        <span
          class="border-brand neon-glow relative flex size-9 shrink-0 overflow-hidden rounded-xl border motion-safe:animate-face-breathe"
        >
          <img src="/logo-face.png" alt="" class="absolute inset-0 h-full w-full object-cover" />
        </span>
        <div class="min-w-0">
          <strong class="text-heading block truncate text-sm">{t('nav.brandName')}</strong><small
            class="text-muted block text-[10px] tracking-widest uppercase"
            >{t('nav.controlCenter')}</small
          >
        </div>
      </a>
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
            : 'text-muted hover:text-heading border-transparent'}">{t(item.labelKey)}</a
        >
      {/each}
    </nav>
    <div class="border-line flex items-center justify-between gap-2 border-t px-4 py-3">
      <span class="text-muted text-xs">{t('nav.theme')}</span>
      <div class="flex items-center gap-2">
        <LanguageToggle />
        <ThemeToggle />
      </div>
    </div>
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize sidebar"
      tabindex="-1"
      class="absolute top-0 right-0 z-10 hidden h-full w-1.5 cursor-col-resize touch-none hover:bg-brand/40 md:block {resizing
        ? 'bg-brand/50'
        : ''}"
      onpointerdown={startResize}
    ></div>
  </aside>
  <div class="min-w-0">
    {#key page.url.pathname}
      <div in:fade={{ duration: transitionDuration }}>
        {@render children()}
      </div>
    {/key}
  </div>
</div>
