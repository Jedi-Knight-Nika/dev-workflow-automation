<script lang="ts">
  import { onMount } from 'svelte';
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
    providers,
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
    providers?: readonly string[];
    onChange?: (value: string | null) => void;
  } = $props();

  let open = $state(false);
  let root: HTMLDivElement;
  const choices = $derived(
    AI_PROVIDERS.filter((provider) => !providers || providers.includes(provider.id))
  );
  const currentLabel = $derived(
    choices.find((provider) => provider.id === value)?.label ?? noneLabel ?? value ?? ariaLabel
  );

  function change(next: string | null) {
    value = next;
    open = false;
    onChange?.(value);
  }

  onMount(() => {
    const closeOutside = (event: PointerEvent) => {
      if (open && event.target instanceof Node && !root.contains(event.target)) open = false;
    };
    document.addEventListener('pointerdown', closeOutside, true);
    return () => document.removeEventListener('pointerdown', closeOutside, true);
  });
</script>

<div class="provider-field" class:compact>
  {#if label}
    <span class="field-label">
      {label}
      {#if hint}<small>{hint}</small>{/if}
    </span>
  {/if}
  <div class="picker" bind:this={root}>
    <button
      {id}
      type="button"
      class="trigger"
      {disabled}
      aria-label={label || ariaLabel}
      aria-haspopup="listbox"
      aria-expanded={open}
      onclick={() => (open = !open)}
    >
      <BrandIcon brand={value || 'ai'} size={compact ? 15 : 17} />
      <span>{currentLabel}</span><i aria-hidden="true">⌄</i>
    </button>
    {#if open}
      <div class="options" role="listbox" aria-label={label || ariaLabel}>
        {#if noneLabel}<button
            type="button"
            role="option"
            aria-selected={!value}
            onclick={() => change(null)}
            ><BrandIcon brand="ai" size={16} /><span>{noneLabel}</span></button
          >{/if}
        {#each choices as provider (provider.id)}
          <button
            type="button"
            role="option"
            aria-selected={value === provider.id}
            onclick={() => change(provider.id)}
            ><BrandIcon brand={provider.id} size={16} /><span>{provider.label}</span
            >{#if value === provider.id}<b>✓</b>{/if}</button
          >
        {/each}
      </div>
    {/if}
  </div>
</div>

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
  .picker {
    position: relative;
    min-width: 0;
  }
  button {
    font: inherit;
  }
  .trigger {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    min-width: 0;
    min-height: 2.65rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    padding: 0.62rem 0.72rem;
    color: var(--color-heading);
    outline: none;
    font-size: 0.72rem;
    cursor: pointer;
    text-align: left;
  }
  .trigger span {
    min-width: 0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .trigger i {
    color: var(--color-muted);
    font-style: normal;
  }
  .trigger:focus-visible {
    border-color: var(--color-brand-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand-2) 18%, transparent);
  }
  .trigger:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
  .options {
    position: absolute;
    z-index: 30;
    top: calc(100% + 0.35rem);
    left: 0;
    width: 100%;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 35%, var(--color-line));
    border-radius: 9px;
    padding: 0.3rem;
    background: var(--color-panel);
    box-shadow: 0 16px 35px -16px rgb(0 0 0 / 75%);
  }
  .options button {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    border: 0;
    border-radius: 6px;
    padding: 0.58rem 0.55rem;
    background: transparent;
    color: var(--color-heading);
    cursor: pointer;
    text-align: left;
    font-size: 0.7rem;
  }
  .options button:hover,
  .options button[aria-selected='true'] {
    background: color-mix(in srgb, var(--color-brand-2) 12%, var(--color-input));
  }
  .options button span {
    flex: 1;
  }
  .options b {
    color: var(--color-accent);
  }
  .compact {
    gap: 0.3rem;
  }
  .compact .trigger {
    min-height: 2.25rem;
    padding-block: 0.48rem;
    font-size: 0.68rem;
  }
</style>
