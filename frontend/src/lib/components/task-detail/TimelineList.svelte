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

  function isStatusEvent(event: TaskEvent): boolean {
    return /TASK_|STATE|NEEDS_HUMAN|PLANNING|IMPLEMENT|REVIEW|WAITING|READY|MERGED|PAUSED|CANCELLED|REOPENED|DONE/.test(
      event.event_type
    );
  }

  function actor(event: TaskEvent): string {
    const payload = event.payload ?? {};
    return String(
      payload.actor_name ?? payload.changed_by ?? payload.user_name ?? event.source ?? 'system'
    );
  }

  const statusEvents = $derived(events.filter(isStatusEvent));
</script>

<section class="border-line rounded-xl border p-5">
  <h2 class="mb-4 font-semibold">{t('taskDetail.timeline')}</h2>
  {#if events.length === 0}
    <p class="text-muted text-sm">{t('taskDetail.noEventsRecorded')}</p>
  {:else}
    {#if statusEvents.length > 0}
      <div class="border-line mb-5 rounded-lg border bg-panel-alt/30 p-3">
        <h3 class="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">
          {t('taskDetail.statusHistory')}
        </h3>
        <div class="space-y-3">
          {#each statusEvents as event (event.id)}
            <div class="flex items-start justify-between gap-3 text-sm">
              <div>
                <strong class={typeClass(event.event_type)}
                  >{event.event_type.replaceAll('_', ' ')}</strong
                >
                <p class="text-muted text-xs">{t('taskDetail.changedBy')} {actor(event)}</p>
              </div>
              <time class="text-muted shrink-0 text-xs" datetime={event.created_at}>
                {new Date(event.created_at).toLocaleString()}
              </time>
            </div>
          {/each}
        </div>
      </div>
    {/if}
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
