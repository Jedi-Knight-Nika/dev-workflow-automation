<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    hover = false,
    padding = 'p-5',
    class: extraClass = '',
    style = '',
    children
  }: {
    hover?: boolean;
    padding?: string;
    class?: string;
    style?: string;
    children: Snippet;
  } = $props();
</script>

<div
  class="border-line bg-panel rounded-xl border {padding} {hover ? 'card-hover' : ''} {extraClass}"
  {style}
>
  {@render children()}
</div>
