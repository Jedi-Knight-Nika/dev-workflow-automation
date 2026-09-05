<script lang="ts">
  let {
    value = $bindable(''),
    label,
    id,
    placeholder = '',
    required = false,
    rows,
    class: extraClass = ''
  }: {
    value?: string;
    label?: string;
    id?: string;
    placeholder?: string;
    required?: boolean;
    rows?: number;
    class?: string;
  } = $props();
</script>

{#if label}<label class="text-muted mb-1.5 block text-xs" for={id}>{label}</label>{/if}
<textarea
  {id}
  {placeholder}
  {required}
  {rows}
  bind:value
  class="border-line w-full resize-y rounded-md border bg-input p-3 text-heading outline-none focus:border-brand {extraClass}"
></textarea>
