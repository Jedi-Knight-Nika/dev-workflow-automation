<script lang="ts">
  let {
    variant = 'inline',
    title,
    message,
    class: extraClass = ''
  }: {
    variant?: 'inline' | 'panel';
    title?: string;
    message: string;
    class?: string;
  } = $props();
</script>

{#if variant === 'panel'}
  <div
    class="border-line text-muted mt-5 flex min-h-[150px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-8 text-center {extraClass}"
  >
    {#if title}<strong class="text-heading">{title}</strong>{/if}
    <span>{message}</span>
  </div>
{:else}
  <p class="text-muted p-8 text-center text-sm {extraClass}">{message}</p>
{/if}
