<script lang="ts">
  import { api } from '$lib/api';
  import type { ProviderModel } from '$lib/ai-model-catalog';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';

  let {
    provider,
    value = $bindable(''),
    label = 'Model',
    disabled = false
  }: { provider: string; value?: string; label?: string; disabled?: boolean } = $props();

  let models = $state<ProviderModel[]>([]);
  let loading = $state(false);
  let custom = $state(false);
  let loadedProvider = $state('');
  let request = 0;

  async function discover() {
    const current = ++request;
    loadedProvider = provider;
    loading = true;
    try {
      const catalog = await api<{ models: ProviderModel[] }>(
        `/providers/${encodeURIComponent(provider)}/catalog`
      );
      if (current !== request) return;
      models = catalog.models;
      custom = !!value && !models.some((model) => model.id === value);
    } catch {
      if (current !== request) return;
      models = [];
      custom = true;
    } finally {
      if (current === request) loading = false;
    }
  }

  $effect(() => {
    if (provider !== loadedProvider) void discover();
  });

  function choose(event: Event) {
    const selected = (event.currentTarget as HTMLSelectElement).value;
    if (selected === '__custom__') custom = true;
    else {
      custom = false;
      value = selected;
    }
  }
</script>

<label class="model-field">
  <span>{label}<small>{loading ? 'Discovering available models…' : 'Provider catalog'}</small></span
  >
  <div class="select-control">
    <BrandIcon brand={provider} size={17} />
    <select
      aria-label={label}
      disabled={disabled || loading}
      value={custom ? '__custom__' : value}
      onchange={choose}
    >
      {#if !value}<option value="" disabled>Select a model</option>{/if}
      {#if value && !models.some((model) => model.id === value) && !custom}<option {value}
          >{value}</option
        >{/if}
      {#each models as model (model.id)}<option value={model.id}
          >{model.display_name || model.id}</option
        >{/each}
      <option value="__custom__">Custom model ID…</option>
    </select>
    <button
      type="button"
      onclick={discover}
      disabled={disabled || loading}
      title="Refresh model catalog"
      aria-label="Refresh model catalog">↻</button
    >
  </div>
  {#if custom}
    <input
      bind:value
      maxlength="255"
      required
      {disabled}
      placeholder="Enter provider model ID"
      aria-label="Custom model ID"
    />
  {/if}
</label>

<style>
  .model-field {
    display: grid;
    gap: 0.35rem;
    color: var(--color-heading);
    font-size: 0.72rem;
  }
  .model-field > span {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
  }
  small {
    color: var(--color-muted);
    font-size: 0.6rem;
    font-weight: 400;
  }
  .select-control {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .select-control :global(.brand-icon) {
    position: absolute;
    z-index: 1;
    left: 0.72rem;
    pointer-events: none;
  }
  select,
  input {
    width: 100%;
    min-width: 0;
    min-height: 2.65rem;
    border: 1px solid var(--color-line);
    border-radius: 8px;
    background: var(--color-input);
    color: var(--color-heading);
    outline: none;
    font: inherit;
  }
  select {
    appearance: none;
    padding: 0.62rem 2rem 0.62rem 2.2rem;
  }
  input {
    padding: 0.62rem 0.72rem;
  }
  select:focus,
  input:focus {
    border-color: var(--color-brand-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand-2) 14%, transparent);
  }
  button {
    flex: 0 0 2.65rem;
    min-height: 2.65rem;
    border: 1px solid var(--color-line);
    border-radius: 8px;
    background: var(--color-input);
    color: var(--color-brand-2);
    cursor: pointer;
  }
  button:hover {
    border-color: var(--color-brand-2);
    box-shadow: 0 0 12px -5px var(--color-brand-2);
  }
  button:disabled {
    cursor: wait;
    opacity: 0.5;
  }
</style>
