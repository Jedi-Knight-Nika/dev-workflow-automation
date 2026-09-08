<script lang="ts">
  import { onMount } from 'svelte';
  import { Handle, Position, type NodeProps } from '@xyflow/svelte';
  import type { LifecycleNodeData } from '$lib/fixed-lifecycle';

  let { id, data }: NodeProps = $props();
  const node = $derived(data as LifecycleNodeData);
  let editing = $state(false);
  let draft = $state('');
  let root: HTMLDivElement;

  onMount(() => {
    const closeOutside = (event: PointerEvent) => {
      if (editing && event.target instanceof Node && !root.contains(event.target)) editing = false;
    };
    document.addEventListener('pointerdown', closeOutside, true);
    return () => document.removeEventListener('pointerdown', closeOutside, true);
  });

  const pixels: Record<string, string[]> = {
    inbox: ['01110', '10001', '10101', '10001', '11111'],
    spark: ['00100', '10101', '01110', '10101', '00100'],
    map: ['10001', '11111', '10101', '11111', '10001'],
    shield: ['11111', '11011', '10101', '01010', '00100'],
    wrench: ['10001', '01010', '00100', '01010', '10001'],
    rocket: ['00100', '01110', '10101', '01110', '10101'],
    chat: ['11110', '10010', '10110', '11110', '01000'],
    merge: ['10001', '11001', '10101', '10011', '10001'],
    check: ['00001', '00010', '10100', '01000', '00000']
  };

  function beginEdit() {
    draft = node.nickname;
    editing = true;
  }

  function save() {
    const value = draft.trim().slice(0, 32);
    if (value) node.onRename(id, value);
    editing = false;
  }
</script>

<Handle type="target" position={Position.Left} />
<div
  bind:this={root}
  class:active={node.active}
  class:waiting={node.waiting}
  class="node-shell"
  style={`--node-color:${node.color}`}
>
  <div class="pixel-avatar" aria-hidden="true">
    {#each pixels[node.icon] ?? pixels.spark as row, y (`${node.icon}-${y}`)}
      {#each row as bit, x (`${node.icon}-${y}-${x}`)}
        {#if bit === '1'}<i style={`--x:${x};--y:${y}`}></i>{/if}
      {/each}
    {/each}
  </div>
  <div class="copy">
    <small>{node.title}</small>
    {#if editing}
      <form
        class="nodrag"
        onsubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <input
          aria-label="Node nickname"
          bind:value={draft}
          maxlength="32"
          onkeydown={(event) => {
            if (event.key === 'Escape') editing = false;
          }}
        />
        <button type="submit" aria-label="Save nickname" title="Save">✓</button>
      </form>
    {:else}
      <div class="name-row">
        <strong>{node.nickname}</strong>
        <button
          class="nodrag edit"
          onclick={beginEdit}
          aria-label="Edit nickname"
          title="Edit nickname">✎</button
        >
      </div>
    {/if}
    {#if node.detail}<span>{node.detail}</span>{/if}
    {#if node.liveTaskId}
      <button
        class="nodrag live"
        onclick={() => node.onOpenLive(node.liveTaskId!, node.nickname)}
        aria-label={`Open live execution for ${node.nickname}`}
        ><i aria-hidden="true"></i> Live</button
      >
    {/if}
  </div>
  <span class="signal" aria-hidden="true"></span>
</div>
<Handle type="source" position={Position.Right} />

<style>
  .node-shell {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.7rem;
    width: 205px;
    min-height: 72px;
    padding: 0.7rem 0.75rem;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--node-color) 42%, var(--color-line));
    border-radius: 12px;
    background:
      linear-gradient(
        135deg,
        color-mix(in srgb, var(--node-color) 10%, transparent),
        transparent 55%
      ),
      var(--color-panel);
    color: var(--color-text);
    box-shadow: 0 8px 24px -18px color-mix(in srgb, var(--node-color) 65%, transparent);
  }
  .node-shell.active {
    border-color: var(--node-color);
    background:
      radial-gradient(
        circle at 16% 30%,
        color-mix(in srgb, var(--node-color) 25%, transparent),
        transparent 44%
      ),
      linear-gradient(
        135deg,
        color-mix(in srgb, var(--node-color) 18%, transparent),
        transparent 62%
      ),
      var(--color-panel);
    box-shadow:
      0 0 0 1px color-mix(in srgb, var(--node-color) 30%, transparent),
      0 0 25px -5px color-mix(in srgb, var(--node-color) 68%, transparent);
    animation: glow 2.6s ease-in-out infinite;
  }
  .node-shell.waiting {
    border-color: color-mix(in srgb, #f7c95c 72%, var(--color-line));
  }
  .pixel-avatar {
    position: relative;
    width: 35px;
    height: 35px;
    flex: 0 0 35px;
    border: 1px solid color-mix(in srgb, var(--node-color) 58%, transparent);
    border-radius: 8px;
    background: color-mix(in srgb, var(--node-color) 12%, var(--color-input));
    image-rendering: pixelated;
  }
  .pixel-avatar i {
    position: absolute;
    left: calc(5px + var(--x) * 5px);
    top: calc(5px + var(--y) * 5px);
    width: 4px;
    height: 4px;
    background: linear-gradient(135deg, white, var(--node-color));
    box-shadow: 0 0 6px color-mix(in srgb, var(--node-color) 80%, transparent);
  }
  .copy {
    min-width: 0;
    flex: 1;
  }
  small,
  span {
    display: block;
  }
  small {
    color: var(--color-muted);
    font-size: 0.6rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }
  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.84rem;
  }
  span {
    margin-top: 0.15rem;
    color: var(--node-color);
    font-size: 0.68rem;
    white-space: pre-line;
  }
  .name-row,
  form {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  button {
    border: 0;
    border-radius: 5px;
    background: transparent;
    color: var(--color-muted);
    cursor: pointer;
    line-height: 1;
  }
  button:hover {
    color: var(--color-brand-2);
    background: color-mix(in srgb, var(--color-brand-2) 12%, transparent);
  }
  input {
    width: 116px;
    border: 1px solid var(--color-brand-2);
    border-radius: 5px;
    padding: 0.18rem 0.3rem;
    background: var(--color-input);
    color: var(--color-text);
    font: inherit;
    font-size: 0.75rem;
    outline: none;
  }
  .live {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    margin-top: 0.35rem;
    padding: 0.2rem 0.4rem;
    color: var(--node-color);
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .live i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--node-color);
    box-shadow: 0 0 8px var(--node-color);
    animation: live-dot 1.2s ease-in-out infinite;
  }
  .signal {
    position: absolute;
    top: 0;
    right: 0;
    width: 5px;
    height: 100%;
    margin: 0;
    background: linear-gradient(180deg, transparent, var(--node-color), transparent);
    opacity: 0;
  }
  .active .signal {
    opacity: 0.9;
    animation: signal 1.7s ease-in-out infinite;
  }
  @keyframes glow {
    50% {
      box-shadow: 0 0 34px -3px color-mix(in srgb, var(--node-color) 78%, transparent);
    }
  }
  @keyframes signal {
    0%,
    100% {
      transform: translateY(-70%);
    }
    50% {
      transform: translateY(70%);
    }
  }
  @keyframes live-dot {
    50% {
      opacity: 0.35;
      transform: scale(0.7);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .node-shell.active,
    .active .signal,
    .live i {
      animation: none;
    }
  }
</style>
