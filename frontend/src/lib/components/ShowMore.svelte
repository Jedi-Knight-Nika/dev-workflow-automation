<script lang="ts" generics="T">
  import Button from '$lib/components/Button.svelte';
  import type { Snippet } from 'svelte';

  let {
    items,
    initialCount = 20,
    step = 20,
    children
  }: {
    items: T[];
    initialCount?: number;
    step?: number;
    children: Snippet<[T[]]>;
  } = $props();

  function initialVisibleCount(): number {
    return initialCount;
  }

  let visibleCount = $state(initialVisibleCount());
  let visibleItems = $derived(items.slice(0, visibleCount));
  let remaining = $derived(items.length - visibleItems.length);
</script>

{@render children(visibleItems)}
{#if remaining > 0}
  <div class="border-line flex justify-center border-t py-3">
    <Button
      size="sm"
      onclick={() => {
        visibleCount += step;
      }}>Show {Math.min(remaining, step)} more ({remaining} left)</Button
    >
  </div>
{/if}
