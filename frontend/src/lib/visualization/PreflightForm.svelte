<script lang="ts">
  import AggregateView from './AggregateView.svelte';
  import FileHistoryNotice from './FileHistoryNotice.svelte';
  import { localDate } from './format';
  import type { Preflight, ViewMode } from './types';

  let {
    scopeChoice = $bindable(),
    choices,
    from = $bindable(),
    to = $bindable(),
    detail = $bindable(),
    mode = $bindable(),
    live = $bindable(),
    showAggregate = $bindable(),
    preflight,
    busy,
    oncheck,
    onstart,
    onclose
  }: {
    scopeChoice: string;
    choices: { value: string; name: string }[];
    from: string;
    to: string;
    detail: number;
    mode: ViewMode;
    live: boolean;
    showAggregate: boolean;
    preflight: Preflight | null;
    busy: boolean;
    oncheck: () => Promise<void>;
    onstart: () => Promise<void>;
    onclose: () => void;
  } = $props();
  function preset(hours: number) {
    from = localDate(new Date(Date.now() - hours * 3600000));
    to = '';
    void oncheck();
  }
</script>

<div class="preflight">
  <p class="intro">Follow tasks, agents, decisions and code changes through recorded history.</p>
  <label
    >Scope<select bind:value={scopeChoice} onchange={oncheck}
      >{#each choices as choice (choice.value)}<option value={choice.value}>{choice.name}</option
        >{/each}</select
    ></label
  >
  <div class="presets">
    <span>Recent</span>{#each [1, 24, 168, 720] as hours (hours)}<button
        onclick={() => preset(hours)}>{hours < 48 ? `${hours}h` : `${hours / 24} days`}</button
      >{/each}
  </div>
  <div class="columns">
    <label
      >From<input type="datetime-local" step="any" bind:value={from} onchange={oncheck} /></label
    ><label
      >Until <small>(blank means now)</small><input
        type="datetime-local"
        step="any"
        bind:value={to}
        onchange={oncheck}
      /></label
    >
  </div>
  <div class="columns">
    <label
      >View<select bind:value={mode}
        ><option value="flow">Task flow</option><option value="workspace">Workspace map</option
        ><option value="code" disabled={detail === 1}>Code changes</option></select
      ></label
    ><label
      >Detail<select bind:value={detail} onchange={oncheck}
        ><option value={1}>Major milestones</option><option value={2}>Engineering detail</option
        ></select
      ></label
    >
  </div>
  <label class="check"
    ><input type="checkbox" bind:checked={live} disabled={!!to} /> Follow live activity</label
  >
  {#if preflight}
    <div class="estimate">
      <strong>{preflight.estimated_events.toLocaleString()}{preflight.too_large ? '+' : ''}</strong>
      events <span>·</span> <strong>{preflight.tasks}</strong> tasks
    </div>
    <FileHistoryNotice history={preflight.file_history} />
    {#each preflight.warnings as warning (warning)}<p class="notice">{warning}</p>{/each}
    {#if preflight.too_large}<button onclick={() => (showAggregate = true)}
        >Open range summary</button
      >
      <p class="notice">
        Choose a smaller scope or time range. This view supports {preflight.max_events.toLocaleString()}
        events, {preflight.max_tasks} tasks and {preflight.max_files.toLocaleString()} file changes.
      </p>{/if}
    {#if showAggregate}<AggregateView
        flight={preflight}
        {detail}
        onrange={(start, end) => {
          from = localDate(start);
          to = localDate(end);
          void oncheck();
        }}
      />{/if}
  {:else if busy}<p role="status">Checking activity history…</p>{/if}
  <p class="hint">
    Read-only history. No agents are started and no AI budget is used. Project groups follow the
    project names already attached to tasks.
  </p>
  <footer>
    <button onclick={onclose}>Cancel</button><button
      class="primary"
      disabled={busy || !preflight || preflight.too_large}
      onclick={onstart}>{busy ? 'Loading…' : 'Start visualization'}</button
    >
  </footer>
</div>

<style>
  .preflight {
    padding: 1.25rem;
    overflow: auto;
  }
  .intro {
    margin-top: 0;
    color: var(--color-muted);
    font-size: 0.85rem;
  }
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }
  .presets {
    display: flex;
    align-items: center;
    gap: 0.65rem;
  }
  .estimate {
    border: 1px solid var(--color-line);
    border-radius: 9px;
    padding: 1rem;
    margin: 1rem 0;
    font-size: 0.85rem;
  }
  .estimate strong {
    color: var(--color-brand-2);
    font-size: 1.2rem;
  }
  .estimate span {
    margin: 0 0.6rem;
  }
  .hint {
    margin: 1rem 0;
    line-height: 1.6;
  }
  .preflight footer {
    justify-content: flex-end;
  }
  button,
  select,
  input:not([type='checkbox']):not([type='range']) {
    border: 1px solid var(--color-line);
    border-radius: 7px;
    background: var(--color-panel-alt);
    color: var(--color-heading);
    padding: 0.45rem 0.65rem;
    font-size: 0.77rem;
  }
  button {
    cursor: pointer;
  }
  button:hover,
  button:focus-visible {
    border-color: var(--color-brand-2);
  }
  button:disabled {
    opacity: 0.45;
    cursor: default;
  }
  button.primary {
    background: var(--color-brand-2);
    border-color: transparent;
    color: #06121a;
    font-weight: 650;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin: 0.85rem 0;
    font-size: 0.8rem;
  }
  .check {
    display: inline-flex;
    flex-direction: row;
    align-items: center;
    margin: 0;
    white-space: nowrap;
    gap: 0.35rem;
    font-size: 0.75rem;
  }
  input[type='checkbox'] {
    accent-color: var(--color-brand-2);
  }
  .hint,
  small {
    color: var(--color-muted);
    font-size: 0.73rem;
  }
  .notice {
    padding: 0.7rem 1rem;
    font-size: 0.8rem;
    color: var(--color-warning);
    background: color-mix(in srgb, var(--color-warning) 8%, transparent);
  }
  footer,
  .presets {
    display: flex;
    align-items: center;
    gap: 0.65rem;
  }
</style>
