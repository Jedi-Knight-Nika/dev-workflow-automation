<script lang="ts">
  import { AI_PROVIDERS } from '$lib/ai-model-catalog';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';

  let {
    value = $bindable('openai'),
    label,
    hint,
    id,
    ariaLabel = 'AI provider',
    noneLabel,
    disabled = false,
    compact = false,
    onChange
  }: {
    value?: string | null;
    label?: string;
    hint?: string;
    id?: string;
    ariaLabel?: string;
    noneLabel?: string;
    disabled?: boolean;
    compact?: boolean;
    onChange?: (value: string | null) => void;
  } = $props();

  function change(event: Event) {
    const next = (event.currentTarget as HTMLSelectElement).value;
    value = noneLabel && !next ? null : next;
    onChange?.(value);
  }
</script>

<label class="provider-field" class:compact>
  {#if label}
    <span class="field-label">
      {label}
      {#if hint}<small>{hint}</small>{/if}
    </span>
  {/if}
  <span class="select-control">
    <BrandIcon brand={value || 'ai'} size={compact ? 15 : 17} />
    <select {id} {disabled} aria-label={label || ariaLabel} value={value || ''} onchange={change}>
      {#if noneLabel}<option value="">{noneLabel}</option>{/if}
      {#each AI_PROVIDERS as provider (provider.id)}
        <option value={provider.id}>{provider.label}</option>
      {/each}
    </select>
    <span class="chevron" aria-hidden="true">⌄</span>
  </span>
</label>

<style>
  .provider-field {
    display: grid;
    min-width: 0;
    gap: 0.42rem;
    color: var(--color-muted);
    font-size: 0.7rem;
  }
  .field-label {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .field-label small {
    color: var(--color-muted);
    font-size: 0.58rem;
  }
  .select-control {
    position: relative;
    display: flex;
    min-width: 0;
    align-items: center;
  }
  .select-control :global(.brand-icon) {
    position: absolute;
    z-index: 1;
    left: 0.72rem;
    pointer-events: none;
  }
  select {
    width: 100%;
    min-width: 0;
    min-height: 2.65rem;
    appearance: none;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    padding: 0.62rem 2rem 0.62rem 2.15rem;
    color: var(--color-heading);
    outline: none;
    font: inherit;
    font-size: 0.72rem;
  }
  select:focus-visible {
    border-color: var(--color-brand-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand-2) 18%, transparent);
  }
  select:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
  .chevron {
    position: absolute;
    right: 0.72rem;
    color: var(--color-muted);
    pointer-events: none;
  }
  .compact {
    gap: 0.3rem;
  }
  .compact select {
    min-height: 2.25rem;
    padding-block: 0.48rem;
    padding-left: 2rem;
    font-size: 0.68rem;
  }
  .compact .select-control :global(.brand-icon) {
    left: 0.65rem;
  }
</style>
