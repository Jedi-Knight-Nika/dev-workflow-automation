<script lang="ts">
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { NAV_ITEMS, isActiveNavItem } from '$lib/nav';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';

  let open = $state(false);

  function close() {
    open = false;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') close();
  }
</script>

<svelte:window onkeydown={open ? handleKeydown : undefined} />

<div
  class="border-line bg-panel-alt flex h-14 items-center justify-between border-b px-4 md:hidden"
>
  <div class="flex items-center gap-2">
    <span
      class="border-brand text-brand neon-glow grid size-7 rounded-xl place-items-center border font-mono text-[10px] font-bold"
      >AW</span
    >
    <strong class="text-heading text-sm">Engineering Worker</strong>
  </div>
  <div class="flex items-center gap-2">
    <ThemeToggle />
    <button
      class="border-line text-muted grid size-9 place-items-center rounded-lg border transition-transform motion-safe:active:scale-[.92]"
      aria-label={open ? 'Close menu' : 'Open menu'}
      aria-expanded={open}
      onclick={() => (open = !open)}
    >
      {#if open}
        <span class="text-lg leading-none">&times;</span>
      {:else}
        <span class="flex flex-col gap-[3px]">
          <span class="block h-[2px] w-4 bg-current"></span>
          <span class="block h-[2px] w-4 bg-current"></span>
          <span class="block h-[2px] w-4 bg-current"></span>
        </span>
      {/if}
    </button>
  </div>
</div>

{#if open}
  <button
    class="fixed inset-0 z-40 bg-black/60 motion-safe:animate-fade-in md:hidden"
    aria-label="Close menu overlay"
    onclick={close}
  ></button>
  <nav
    class="border-line bg-panel-alt fixed inset-y-0 left-0 z-50 flex w-64 flex-col gap-1 rounded-r-2xl border-r p-4 shadow-[8px_0_24px_rgba(0,0,0,.4)] motion-safe:animate-slide-in-left md:hidden"
  >
    <div class="border-line mb-3 flex h-12 items-center gap-2 border-b pb-3">
      <span
        class="border-brand text-brand neon-glow grid size-8 rounded-xl place-items-center border font-mono text-[10px] font-bold"
        >AW</span
      >
      <strong class="text-heading text-sm">Engineering Worker</strong>
    </div>
    {#each NAV_ITEMS as item (item.href)}
      <a
        href={resolve(item.href)}
        onclick={close}
        class="min-h-[2.75rem] rounded-lg border-l-2 px-3 py-2.5 text-sm transition-colors {isActiveNavItem(
          page.url.pathname,
          item.href
        )
          ? 'border-brand bg-panel text-heading'
          : 'text-muted hover:text-heading border-transparent'}"
      >
        {item.label}
      </a>
    {/each}
  </nav>
{/if}
