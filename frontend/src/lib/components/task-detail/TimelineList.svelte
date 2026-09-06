<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { TaskEvent } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';

  let { events }: { events: TaskEvent[] } = $props();

  function typeClass(eventType: string): string {
    if (/FAIL|ERROR|CANCEL|BLOCK/.test(eventType)) return 'text-danger';
    if (/SUCCEED|MERGED|COMPLETE|READY/.test(eventType)) return 'text-accent';
    if (/RETRY|WAIT|PAUSE|NEEDS_HUMAN/.test(eventType)) return 'text-warning';
    return 'text-heading';
  }
</script>

<section class="border-line rounded-xl border p-5">
  <h2 class="mb-4 font-semibold">{t('taskDetail.timeline')}</h2>
  {#if events.length === 0}
    <p class="text-muted text-sm">{t('taskDetail.noEventsRecorded')}</p>
  {:else}
    <ShowMore items={events}>
      {#snippet children(visibleEvents: TaskEvent[])}
        {#each visibleEvents as event, index (event.id)}
          <div
            class="border-line border-l pb-5 pl-4 motion-safe:animate-fade-in-up"
            style="animation-delay: {Math.min(index, 10) * 30}ms"
          >
            <strong class="text-sm {typeClass(event.event_type)}"
              >{event.event_type.replaceAll('_', ' ')}</strong
            >
            <p class="text-muted text-xs">
              {event.source} · {new Date(event.created_at).toLocaleString()}
            </p>
          </div>
        {/each}
      {/snippet}
    </ShowMore>
  {/if}
</section>
