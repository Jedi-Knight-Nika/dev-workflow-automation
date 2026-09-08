<script lang="ts">
  import ShowMore from '$lib/components/ShowMore.svelte';
  import type { TaskEvent } from '$lib/types';
  let { events }: { events: TaskEvent[] } = $props();
  const changes = $derived(events.filter((event) => event.event_type === 'TASK_LIFECYCLE_CHANGED'));
  function actor(event: TaskEvent) {
    return String(event.payload.actor ?? event.source);
  }
</script>

<section class="border-line space-y-5 rounded-xl border p-5">
  <h2 class="font-semibold">Status history</h2>
  {#if !changes.length}<p class="text-muted text-sm">No status transitions recorded.</p>{/if}
  <ShowMore items={changes}>
    {#snippet children(visible: TaskEvent[])}
      {#each visible as event (event.id)}
        <article class="border-line border-l-2 pb-4 pl-4 text-sm">
          <p>
            {event.payload.from_status} / {event.payload.from_stage} →
            <strong>{event.payload.to_status} / {event.payload.to_stage}</strong>
          </p>
          <p class="text-muted text-xs">
            Changed by {actor(event)} ·
            <time datetime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
          </p>
          {#if event.payload.wait_reason && event.payload.wait_reason !== 'NONE'}<p
              class="text-warning text-xs"
            >
              {String(event.payload.wait_reason).replaceAll('_', ' ')}
            </p>{/if}
        </article>
      {/each}
    {/snippet}
  </ShowMore>
  <details>
    <summary class="cursor-pointer font-medium">All events ({events.length})</summary>
    <ShowMore items={events}>
      {#snippet children(visible: TaskEvent[])}
        {#each visible as event (event.id)}
          <article class="border-line border-b py-3 text-sm">
            <p>{event.event_type.replaceAll('_', ' ')}</p>
            {#if event.payload.reason || event.payload.message}
              <p class="mt-1 whitespace-pre-wrap break-words">
                {String(event.payload.reason ?? event.payload.message)}
              </p>
            {/if}
            <p class="text-muted text-xs">
              {actor(event)} ·
              <time datetime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
            </p>
          </article>
        {/each}
      {/snippet}
    </ShowMore>
  </details>
</section>
