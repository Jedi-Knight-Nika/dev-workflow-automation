<script lang="ts">
  import {
    ACCENT_ORDER,
    accentPreview,
    customHuePreview,
    getAccentId,
    getCustomHue,
    setAccentId,
    setCustomHue,
    type AccentId
  } from '$lib/accent.svelte';
  import { t } from '$lib/i18n/index.svelte';

  function label(id: AccentId): string {
    return t(`accent.${id}` as const);
  }

  let track: HTMLDivElement;
  let dragging = $state(false);

  function hueFromPointer(clientX: number): number {
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(ratio * 360);
  }

  function handleMove(event: PointerEvent) {
    setCustomHue(hueFromPointer(event.clientX));
  }

  function handleUp() {
    dragging = false;
    window.removeEventListener('pointermove', handleMove);
    window.removeEventListener('pointerup', handleUp);
  }

  function startDrag(event: PointerEvent) {
    event.preventDefault();
    dragging = true;
    setCustomHue(hueFromPointer(event.clientX));
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
  }

  function nudge(delta: number) {
    setCustomHue(getCustomHue() + delta);
  }

  const customPreview = $derived(customHuePreview(getCustomHue()));
</script>

<section class="panel">
  <h2>{t('accent.title')}</h2>
  <p>{t('accent.description')}</p>
  <div class="swatches">
    {#each ACCENT_ORDER as id (id)}
      {@const colors = accentPreview(id)}
      <button
        type="button"
        class="swatch"
        class:active={getAccentId() === id}
        style={`--swatch-a: ${colors.brand}; --swatch-b: ${colors.brand2};`}
        onclick={() => setAccentId(id)}
        aria-pressed={getAccentId() === id}
        title={label(id)}
      >
        <span class="dot"></span>
        <span class="label">{label(id)}</span>
      </button>
    {/each}
  </div>
  <div class="custom" class:active={getAccentId() === 'custom'}>
    <div class="custom-header">
      <span class="custom-label">{t('accent.customLabel')}</span>
      <span class="custom-hint">{t('accent.customHint')}</span>
    </div>
    <div
      class="track"
      class:dragging
      bind:this={track}
      onpointerdown={startDrag}
      role="slider"
      tabindex="0"
      aria-label={t('accent.hueSlider')}
      aria-valuemin={0}
      aria-valuemax={360}
      aria-valuenow={getCustomHue()}
      onkeydown={(event) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowUp') nudge(4);
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') nudge(-4);
      }}
    >
      <div
        class="handle"
        class:dragging
        style={`left: ${(getCustomHue() / 360) * 100}%; --swatch-a: ${customPreview.brand}; --swatch-b: ${customPreview.brand2};`}
      ></div>
    </div>
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
  .swatches {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    margin-top: 1rem;
  }
  .swatch {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.4rem 0.9rem 0.4rem 0.4rem;
    background: var(--color-input);
    color: var(--color-text);
    cursor: pointer;
    transition:
      border-color 0.2s var(--ease-smooth),
      box-shadow 0.2s var(--ease-smooth),
      transform 0.15s var(--ease-smooth);
  }
  .swatch:hover {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--swatch-a) 55%, var(--color-line));
  }
  .swatch.active {
    border-color: var(--swatch-a);
    box-shadow: 0 0 16px -3px color-mix(in srgb, var(--swatch-a) 65%, transparent);
  }
  .dot {
    display: block;
    width: 1.4rem;
    height: 1.4rem;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--swatch-a), var(--swatch-b));
    box-shadow: 0 0 10px -2px color-mix(in srgb, var(--swatch-a) 70%, transparent);
  }
  .label {
    font-size: 0.8rem;
  }

  .custom {
    margin-top: 1.1rem;
    padding: 0.9rem 1rem 1.1rem;
    border: 1px solid var(--color-line);
    border-radius: 0.85rem;
    background: var(--color-panel-alt);
    transition: border-color 0.25s var(--ease-smooth);
  }
  .custom.active {
    border-color: color-mix(in srgb, var(--color-brand) 55%, var(--color-line));
  }
  .custom-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.6rem;
    margin-bottom: 0.7rem;
  }
  .custom-label {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--color-heading);
  }
  .custom-hint {
    font-size: 0.72rem;
    color: var(--color-muted);
  }
  .track {
    position: relative;
    height: 1.1rem;
    border-radius: 999px;
    background: linear-gradient(
      90deg,
      #ff0000,
      #ffff00,
      #00ff00,
      #00ffff,
      #0000ff,
      #ff00ff,
      #ff0000
    );
    cursor: grab;
    touch-action: none;
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--color-line) 80%, transparent);
  }
  .track.dragging {
    cursor: grabbing;
  }
  .handle {
    position: absolute;
    top: 50%;
    width: 1.6rem;
    height: 1.6rem;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    background: linear-gradient(135deg, var(--swatch-a), var(--swatch-b));
    border: 2px solid white;
    box-shadow:
      0 0 0 1px color-mix(in srgb, var(--swatch-a) 60%, transparent),
      0 0 14px -2px color-mix(in srgb, var(--swatch-a) 75%, transparent);
    cursor: grab;
    transition: box-shadow 0.2s var(--ease-smooth);
  }
  .handle.dragging {
    cursor: grabbing;
    box-shadow:
      0 0 0 2px color-mix(in srgb, var(--swatch-a) 75%, transparent),
      0 0 22px -2px color-mix(in srgb, var(--swatch-a) 85%, transparent);
  }
</style>
