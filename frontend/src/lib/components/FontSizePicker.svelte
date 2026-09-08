<script lang="ts">
  import {
    DEFAULT_FONT_SIZE,
    getFontSize,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    setFontSize
  } from '$lib/font-size.svelte';
  import { t } from '$lib/i18n/index.svelte';
</script>

<section class="panel" aria-labelledby="font-size-title">
  <div class="header">
    <div>
      <h2 id="font-size-title">{t('fontSize.title')}</h2>
      <p>{t('fontSize.description')}</p>
    </div>
    <output for="font-size-slider">{getFontSize()}px</output>
  </div>
  <div class="slider-row">
    <span class="small" aria-hidden="true">A</span>
    <input
      id="font-size-slider"
      type="range"
      class="track"
      min={MIN_FONT_SIZE}
      max={MAX_FONT_SIZE}
      step="1"
      value={getFontSize()}
      aria-label={t('fontSize.slider')}
      aria-valuetext={t('fontSize.value', { size: getFontSize() })}
      oninput={(event) => setFontSize(event.currentTarget.valueAsNumber)}
    />
    <span class="large" aria-hidden="true">A</span>
  </div>
  <p class="hint">{t('fontSize.defaultHint', { size: DEFAULT_FONT_SIZE })}</p>
</section>

<style>
  .panel {
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
    padding: 1.25rem;
  }
  .header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  h2 {
    margin-bottom: 0.5rem;
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--color-heading);
  }
  p {
    font-size: 0.85rem;
    color: var(--color-muted);
  }
  output {
    flex: none;
    border: 1px solid color-mix(in srgb, var(--color-brand) 45%, var(--color-line));
    border-radius: 999px;
    padding: 0.2rem 0.55rem;
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--color-brand);
  }
  .slider-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 0.75rem;
    margin-top: 1.25rem;
  }
  .small,
  .large {
    color: var(--color-heading);
    font-weight: 700;
    line-height: 1;
  }
  .small {
    font-size: 0.8rem;
  }
  .large {
    font-size: 1.25rem;
  }
  .track {
    appearance: none;
    width: 100%;
    height: 0.5rem;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--color-brand), var(--color-brand-2));
    cursor: pointer;
  }
  .track::-webkit-slider-thumb {
    appearance: none;
    width: 1.25rem;
    height: 1.25rem;
    border: 2px solid var(--color-panel);
    border-radius: 50%;
    background: var(--color-heading);
    box-shadow: 0 0 0 1px var(--color-brand);
  }
  .track::-moz-range-thumb {
    width: 1rem;
    height: 1rem;
    border: 2px solid var(--color-panel);
    border-radius: 50%;
    background: var(--color-heading);
    box-shadow: 0 0 0 1px var(--color-brand);
  }
  .track:focus-visible {
    outline: 2px solid var(--color-heading);
    outline-offset: 4px;
  }
  .hint {
    margin-top: 0.75rem;
    font-size: 0.75rem;
  }
</style>
