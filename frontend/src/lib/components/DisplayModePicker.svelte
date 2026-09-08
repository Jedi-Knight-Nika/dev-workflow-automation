<script lang="ts">
  import { getDisplayMode, setDisplayMode, type DisplayMode } from '$lib/display.svelte';
  import { t } from '$lib/i18n/index.svelte';

  const options = $derived<{ id: DisplayMode; label: string; hint: string }[]>([
    { id: 'default', label: t('display.default'), hint: t('display.defaultHint') },
    { id: 'jarvis', label: t('display.jarvis'), hint: t('display.jarvisHint') }
  ]);
</script>

<section class="panel">
  <h2>{t('display.title')}</h2>
  <p>{t('display.description')}</p>
  <div class="options">
    {#each options as option (option.id)}
      <button
        type="button"
        class="option"
        class:active={getDisplayMode() === option.id}
        onclick={() => setDisplayMode(option.id)}
        aria-pressed={getDisplayMode() === option.id}
      >
        <span class="label">{option.label}</span>
        <span class="hint">{option.hint}</span>
      </button>
    {/each}
  </div>
</section>

<style>
  .panel {
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
    padding: 1.25rem;
  }
  h2 {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--color-heading);
    margin-bottom: 0.5rem;
  }
  p {
    font-size: 0.85rem;
    color: var(--color-muted);
  }
  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    margin-top: 1rem;
  }
  .option {
    display: grid;
    gap: 0.15rem;
    min-width: 140px;
    border: 1px solid var(--color-line);
    border-radius: 0.7rem;
    padding: 0.6rem 0.9rem;
    background: var(--color-input);
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.2s var(--ease-smooth),
      box-shadow 0.2s var(--ease-smooth),
      transform 0.15s var(--ease-smooth);
  }
  .option:hover {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--color-brand-2) 50%, var(--color-line));
  }
  .option.active {
    border-color: var(--color-brand);
    box-shadow: 0 0 16px -3px color-mix(in srgb, var(--color-brand) 55%, transparent);
  }
  .label {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--color-heading);
  }
  .hint {
    font-size: 0.7rem;
    color: var(--color-muted);
  }
</style>
