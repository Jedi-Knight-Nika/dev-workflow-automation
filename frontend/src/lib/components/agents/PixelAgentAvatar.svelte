<script lang="ts">
  let {
    seed,
    size = 40,
    label = 'AI agent'
  }: { seed: string; size?: number; label?: string } = $props();

  const palettes = [
    ['#221047', '#A970FF', '#45E0C1'],
    ['#102847', '#48A7FF', '#FFD166'],
    ['#40152D', '#FF5D9E', '#7EF0D2'],
    ['#3E2510', '#FF9F43', '#7CFFCB'],
    ['#172E19', '#63D471', '#D6FF73'],
    ['#30124A', '#E879F9', '#67E8F9']
  ];

  function hash(value: string) {
    let result = 2166136261;
    for (const character of value) {
      result ^= character.charCodeAt(0);
      result = Math.imul(result, 16777619);
    }
    return result >>> 0;
  }

  function portrait(value: string) {
    const identity = hash(value || 'agent');
    const palette = palettes[identity % palettes.length];
    const cells: { x: number; y: number; color: string }[] = [];
    for (let y = 0; y < 5; y += 1) {
      for (let x = 0; x < 3; x += 1) {
        const bit = (identity >>> ((y * 3 + x) % 28)) & 1;
        if (!bit && !(y === 2 && x === 1)) continue;
        const color = (identity >>> ((x + y) % 20)) & 1 ? palette[1] : palette[2];
        cells.push({ x, y, color });
        if (x < 2) cells.push({ x: 4 - x, y, color });
      }
    }
    return { palette, cells };
  }

  const avatar = $derived(portrait(seed));
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 7 7"
  role="img"
  aria-label={`${label} pixel avatar`}
  shape-rendering="crispEdges"
  class="avatar"
>
  <rect width="7" height="7" rx="1" fill={avatar.palette[0]} />
  {#each avatar.cells as cell, index (`${cell.x}-${cell.y}-${index}`)}
    <rect x={cell.x + 1} y={cell.y + 1} width="1" height="1" fill={cell.color} />
  {/each}
  <rect x="2" y="3" width="1" height="1" fill="#fff" />
  <rect x="4" y="3" width="1" height="1" fill="#fff" />
</svg>

<style>
  .avatar {
    flex: none;
    border: 1px solid color-mix(in srgb, white 16%, transparent);
    border-radius: 22%;
    box-shadow: 0 5px 16px color-mix(in srgb, black 25%, transparent);
  }
</style>
