<script lang="ts">
  import { onMount } from 'svelte';
  import type { AppNotification } from '$lib/types';
  import { listNotifications, markNotification, unreadCount } from '$lib/services/notifications';

  let open = $state(false);
  let count = $state(0);
  let items = $state<AppNotification[]>([]);

  async function refresh() {
    try {
      [items, { count }] = await Promise.all([listNotifications(), unreadCount()]);
    } catch {
      // The notification channel must not interfere with normal navigation.
    }
  }
  async function mark(item: AppNotification, action: 'read' | 'acknowledge') {
    await markNotification(item.id, action);
    await refresh();
  }
  onMount(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  });
</script>

<div class="fixed top-4 right-4 z-50">
  <button
    class="border-line bg-panel text-heading relative size-11 rounded-xl border shadow-xl"
    aria-label="Notifications"
    aria-expanded={open}
    onclick={() => (open = !open)}
    >♢
    {#if count}<b
        class="bg-danger absolute -top-2 -right-2 rounded-full px-1.5 py-0.5 text-[10px] text-white"
        >{count > 99 ? '99+' : count}</b
      >{/if}
  </button>
  {#if open}
    <section
      class="border-line bg-panel absolute top-14 right-0 max-h-[75vh] w-[min(25rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border shadow-2xl"
    >
      <header
        class="border-line sticky top-0 flex items-center justify-between border-b bg-inherit p-4"
      >
        <div>
          <small class="text-brand tracking-widest">ATTENTION CENTER</small>
          <h2 class="text-heading font-semibold">Notifications</h2>
        </div>
        <b class="text-muted text-xs">{count} unread</b>
      </header>
      {#each items as item (item.id)}
        <article
          class="border-line border-b p-4"
          class:border-l-4={item.status === 'UNREAD'}
          class:border-l-brand={item.severity !== 'CRITICAL'}
          class:border-l-danger={item.severity === 'CRITICAL'}
        >
          <small class="text-muted tracking-wider">{item.severity.replaceAll('_', ' ')}</small>
          <strong class="text-heading mt-1 block text-sm">{item.title}</strong>
          <p class="text-muted mt-1 text-xs leading-relaxed">{item.message}</p>
          <footer class="mt-3 flex gap-2">
            {#if item.action_target}
              <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
              <a class="border-line rounded-md border px-2 py-1 text-xs" href={item.action_target}
                >Open</a
              >
            {/if}
            {#if item.status === 'UNREAD'}<button
                class="border-line rounded-md border px-2 py-1 text-xs"
                onclick={() => void mark(item, 'read')}>Read</button
              >{/if}
            {#if !['ACKNOWLEDGED', 'RESOLVED'].includes(item.status)}<button
                class="border-line rounded-md border px-2 py-1 text-xs"
                onclick={() => void mark(item, 'acknowledge')}>Acknowledge</button
              >{/if}
          </footer>
        </article>
      {:else}<p class="text-muted p-5 text-sm">No notifications. The system is quiet.</p>{/each}
    </section>
  {/if}
</div>
