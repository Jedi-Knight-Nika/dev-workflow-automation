<script lang="ts">
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
  const navigation = [
    ['/', 'Dashboard'],
    ['/tasks', 'Tasks'],
    ['/repositories', 'Repositories'],
    ['/agents', 'Agents'],
    ['/integrations', 'Integrations'],
    ['/settings', 'Settings']
  ] as const;
</script>

<div class="min-h-screen md:grid md:grid-cols-[220px_1fr]">
  <aside class="border-line border-b bg-[#0d110f] md:min-h-screen md:border-r md:border-b-0">
    <div class="border-line flex h-[72px] items-center gap-3 border-b px-5">
      <span
        class="border-accent text-accent grid size-9 place-items-center border font-mono text-[11px] font-bold"
        >AW</span
      >
      <div>
        <strong class="block text-sm">Engineering Worker</strong><small
          class="text-[10px] tracking-widest text-[#758078] uppercase">Control center</small
        >
      </div>
    </div>
    <nav class="flex overflow-x-auto p-3 md:block md:space-y-1">
      {#each navigation as item (item[0])}
        <a
          href={resolve(item[0])}
          class="block shrink-0 border-l-2 px-3 py-2.5 text-sm transition {page.url.pathname ===
            item[0] ||
          (item[0] !== '/' && page.url.pathname.startsWith(item[0]))
            ? 'border-accent bg-[#151c18] text-white'
            : 'border-transparent text-[#7f8982] hover:text-white'}">{item[1]}</a
        >
      {/each}
    </nav>
  </aside>
  <div class="min-w-0">{@render children()}</div>
</div>
