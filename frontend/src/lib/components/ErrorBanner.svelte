<script lang="ts">
  let { message, class: extraClass = '' }: { message: string; class?: string } = $props();
</script>

{#if message}
  <p
    class="text-danger border-danger/30 rounded-lg border p-3 text-sm {extraClass}"
    style="background: color-mix(in srgb, var(--color-danger) 12%, var(--color-panel));"
  >
    {message}
  </p>
{/if}
