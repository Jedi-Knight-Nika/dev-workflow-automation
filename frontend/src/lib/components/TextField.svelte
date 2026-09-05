<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';

  let {
    value = $bindable(''),
    label,
    id,
    placeholder = '',
    type = 'text',
    required = false,
    autocomplete,
    pattern,
    title,
    inputmode,
    maxlength,
    class: extraClass = ''
  }: {
    value?: string;
    label?: string;
    id?: string;
    placeholder?: string;
    type?: string;
    required?: boolean;
    autocomplete?: HTMLInputAttributes['autocomplete'];
    pattern?: string;
    title?: string;
    inputmode?: 'none' | 'text' | 'tel' | 'url' | 'email' | 'numeric' | 'decimal' | 'search';
    maxlength?: number;
    class?: string;
  } = $props();
</script>

{#if label}<label class="text-muted mb-1.5 block text-xs" for={id}>{label}</label>{/if}
<input
  {id}
  {type}
  {placeholder}
  {required}
  {autocomplete}
  {pattern}
  {title}
  {inputmode}
  {maxlength}
  bind:value
  class="border-line w-full rounded-md border bg-input p-3 text-heading outline-none focus:border-brand {extraClass}"
/>
