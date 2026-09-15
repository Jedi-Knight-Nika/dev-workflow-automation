<script lang="ts">
  import { untrack } from 'svelte';
  import { resolve } from '$app/paths';
  import { activityApi } from './api';
  import { money, title } from './format';
  import { receiptsBefore } from './receipts';
  import type { ActivityEvent, Inspection, Preflight } from './types';
  let {
    selected,
    flight,
    detail,
    sequences,
    events,
    onseek
  }: {
    selected: ActivityEvent | null;
    flight: Preflight;
    detail: number;
    sequences: Set<number>;
    events: ActivityEvent[];
    onseek: (sequence: number) => void;
  } = $props();
  let inspection = $state<Inspection | null>(null),
    error = $state(''),
    loading = $state(false);
  const facts = $derived(
    Object.entries(selected?.payload ?? {}).filter(
      ([, value]) => value !== null && ['string', 'number', 'boolean'].includes(typeof value)
    )
  );
  const selectedSequence = $derived(selected?.sequence ?? null);
  const receiptEvent = $derived(
    events.find((event) => event.sequence === selectedSequence) ?? null
  );
  const receipts = $derived(receiptsBefore(events, receiptEvent));
  const snapshot = $derived(
    `${flight.scope.type}:${flight.scope.id}:${flight.from}:${flight.to}:${flight.through_sequence}:${detail}`
  );
  $effect(() => {
    const sequence = selectedSequence;
    // Camera frames clone event objects; only selection or snapshot changes require a read.
    void snapshot;
    inspection = null;
    error = '';
    loading = false;
    if (sequence === null) return;
    const request = new AbortController();
    loading = true;
    void untrack(() => activityApi.inspect(flight, detail, sequence, request.signal))
      .then((value) => {
        if (!request.signal.aborted) inspection = value;
      })
      .catch(() => {
        if (!request.signal.aborted)
          error = 'Related details could not be loaded. Recorded event facts remain available.';
      })
      .finally(() => {
        if (!request.signal.aborted) loading = false;
      });
    return () => request.abort();
  });
</script>

<section aria-label="Activity inspector">
  <h3>{selected ? title(selected.kind) : 'Select an event'}</h3>
  {#if selected}
    <p>{selected.actor} · {selected.actor_type}</p>
    <p>
      {selected.team_name ?? 'Unassigned Team'} · {selected.project ?? 'Workspace'} · {new Date(
        selected.occurred_at
      ).toLocaleString()}
    </p>
    <p>
      Task receipts before this event in the selected range: {money(
        receipts.cost
      )}{receipts.unknownCosts ? ` + ${receipts.unknownCosts} unknown` : ''}
    </p>
    <p>
      <a href={resolve(`/tasks/${selected.task_id}#execution-details`)}>Open technical details ↗</a>
    </p>
    <a href={resolve('/tasks/[id]', { id: selected.task_id })}
      >{selected.task_key || selected.task_title} ↗</a
    >
    <dl>
      {#each facts as [key, value] (key)}<div>
          <dt>{title(key)}</dt>
          <dd>{String(value)}</dd>
        </div>{/each}
      {#if selected.correlation_id}<div>
          <dt>Correlation</dt>
          <dd>{selected.correlation_id}</dd>
        </div>{/if}
    </dl>
    {#each selected.files as file (file.repository_id + file.path)}<p class="file">
        <b>{file.operation}</b>
        {file.previous_path ? `${file.previous_path} → ` : ''}{file.path}
        <small>+{file.lines_added ?? '?'} / −{file.lines_deleted ?? '?'}</small>
      </p>{/each}
    {#if loading}<p role="status">Loading related activity…</p>{/if}
    {#if error}<p>{error}</p>{/if}
    {#if inspection}
      {#each [{ name: 'Recorded causes and references', items: inspection.event.parents ?? [] }, { name: 'Linked follow-up activity', items: inspection.children }, { name: 'Checks on the same revision', items: inspection.checks }] as group (group.name)}
        <h4>{group.name}</h4>
        {#each group.items as item, index (index)}
          <p>
            {#if sequences.has(item.sequence)}<button onclick={() => onseek(item.sequence)}
                >{title(item.kind)}</button
              >{:else}{title(item.kind)} (outside this view){/if}
            · {item.actor} · {new Date(item.occurred_at).toLocaleString()}
            {#if item.relationship}
              · {title(item.relationship)}{/if}
            {#if item.payload.check_kind}
              · {String(item.payload.check_kind)}: {String(item.payload.status)}{/if}
          </p>
        {:else}<p>No recorded links.</p>{/each}
      {/each}
      {#if inspection.event.unresolved_parents}<p>
          {inspection.event.unresolved_parents} references are unavailable in this snapshot.
        </p>{/if}
      {#if inspection.truncated}<p>Showing the first 50 related records per group.</p>{/if}
      {#if inspection.file_status}<p>
          File collection: {title(inspection.file_status)} · {inspection.file_attempts} attempts{inspection.file_retry_at
            ? ` · next retry ${new Date(inspection.file_retry_at).toLocaleString()}`
            : ''}
        </p>{/if}
    {/if}
  {:else}<p>
      Use the canvas or timeline to inspect recorded facts. An unknown starting state means earlier
      history was not available.
    </p>{/if}
</section>

<style>
  section {
    overflow: auto;
    padding: 0.9rem 1rem;
    font-size: 0.78rem;
  }
  h3,
  h4 {
    margin: 0 0 0.5rem;
  }
  h4 {
    margin-top: 1rem;
  }
  p,
  dt {
    color: var(--color-muted);
  }
  a,
  button {
    color: var(--color-brand-2);
  }
  button {
    background: transparent;
    border: 0;
    text-decoration: underline;
    cursor: pointer;
    padding: 0;
    font: inherit;
  }
  dl div {
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: 0.5rem;
    padding: 0.2rem 0;
  }
  dt {
    text-transform: capitalize;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .file {
    overflow-wrap: anywhere;
  }
</style>
