<script lang="ts">
  import { onDestroy, type Component } from 'svelte';
  import { page } from '$app/state';
  import type { Scope } from './types';
  let Viewer = $state<Component<{ scope: Scope; onclose: () => void }> | null>(null);
  let loading = $state(false),
    error = $state('');
  let disposed = false;
  const match = $derived(page.url.pathname.match(/^\/(teams|tasks)\/([0-9a-f-]+)$/i));
  const available = $derived(
    page.url.pathname === '/' || !!match || page.url.pathname === '/repositories'
  );
  const scope = $derived<Scope>(
    match ? { type: match[1] === 'teams' ? 'team' : 'task', id: match[2] } : { type: 'workspace' }
  );
  async function open() {
    loading = true;
    error = '';
    try {
      const module = await import('./VisualizerShell.svelte');
      if (!disposed) Viewer = module.default;
    } catch {
      if (!disposed) error = 'Activity visualization could not load. Try again.';
    } finally {
      if (!disposed) loading = false;
    }
  }
  onDestroy(() => {
    disposed = true;
  });
</script>

{#if available}
  <div class="activity-entry">
    <button type="button" onclick={open} disabled={loading} aria-haspopup="dialog">
      <span aria-hidden="true">◉</span>
      {loading ? 'Opening activity…' : 'Visualize activity'}
    </button>
    {#if error}<span role="alert">{error}</span>{/if}
  </div>
{/if}
{#if Viewer}<Viewer {scope} onclose={() => (Viewer = null)} />{/if}

<style>
  .activity-entry {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 1rem;
    padding: 0.65rem 1.5rem;
    border-bottom: 1px solid var(--color-line);
    background: var(--color-panel-alt);
  }
  button {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.45rem 0.8rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    color: var(--color-heading);
    font-size: 0.8rem;
    cursor: pointer;
  }
  button:hover {
    border-color: var(--color-brand-2);
  }
  button span {
    color: var(--color-brand-2);
  }
  [role='alert'] {
    color: var(--color-danger);
    font-size: 0.8rem;
  }
</style>
