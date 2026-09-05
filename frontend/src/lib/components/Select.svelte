<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    value = $bindable(''),
    label,
    id,
    required = false,
    ariaLabel,
    class: extraClass = '',
    children
  }: {
    value?: string;
    label?: string;
    id?: string;
    required?: boolean;
    ariaLabel?: string;
    class?: string;
    children: Snippet;
  } = $props();
</script>

{#if label}<label class="text-muted mb-1.5 block text-xs" for={id}>{label}</label>{/if}
<select
  {id}
  {required}
  aria-label={ariaLabel}
  bind:value
  class="border-line w-full rounded-md border bg-input p-3 text-heading outline-none focus:border-brand {extraClass}"
>
  {@render children()}
</select>
