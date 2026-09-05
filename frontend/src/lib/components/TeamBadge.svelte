<script lang="ts">
  let {
    id,
    name,
    compact = false
  }: { id?: string | null; name?: string | null; compact?: boolean } = $props();
  const icons = ['⚡', '◆', '▲', '●', '✦', '⬢', '◈', '▣'];
  const palettes = ['violet', 'cyan', 'amber', 'green', 'rose', 'blue'];
  const hash = $derived(
    [...(id || name || 'unassigned')].reduce(
      (total, character) => total + character.charCodeAt(0),
      0
    )
  );
</script>

<span
  class="badge"
  class:compact
  class:unassigned={!id}
  data-palette={palettes[hash % palettes.length]}
>
  <span class="icon" aria-hidden="true">{id ? icons[hash % icons.length] : '○'}</span>
  <span>{name || 'Unassigned'}</span>
</span>

<style>
  .badge {
    display: inline-flex;
    min-width: 0;
    align-items: center;
    gap: 0.38rem;
    border: 1px solid color-mix(in srgb, var(--team-color) 30%, var(--color-line));
    border-radius: 999px;
    background: color-mix(in srgb, var(--team-color) 9%, var(--color-panel));
    padding: 0.25rem 0.55rem 0.25rem 0.3rem;
    color: var(--color-text);
    font-size: 0.69rem;
    font-weight: 700;
  }
  .icon {
    display: grid;
    width: 1.25rem;
    height: 1.25rem;
    place-items: center;
    border-radius: 50%;
    background: color-mix(in srgb, var(--team-color) 18%, var(--color-panel));
    color: var(--team-color);
    font-size: 0.66rem;
  }
  .compact {
    padding: 0.16rem 0.42rem 0.16rem 0.22rem;
    font-size: 0.63rem;
  }
  .compact .icon {
    width: 1rem;
    height: 1rem;
  }
  .unassigned {
    --team-color: var(--color-muted) !important;
    border-style: dashed;
    font-weight: 600;
    color: var(--color-muted);
  }
  [data-palette='violet'] {
    --team-color: #7c5cff;
  }
  [data-palette='cyan'] {
    --team-color: #0891b2;
  }
  [data-palette='amber'] {
    --team-color: #d97706;
  }
  [data-palette='green'] {
    --team-color: #059669;
  }
  [data-palette='rose'] {
    --team-color: #e11d48;
  }
  [data-palette='blue'] {
    --team-color: #2563eb;
  }
</style>
