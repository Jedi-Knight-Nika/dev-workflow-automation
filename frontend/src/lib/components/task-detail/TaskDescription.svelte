<script lang="ts">
  import { taskDescriptionParts } from '$lib/task-links';
  let { description, sourceUrl = null }: { description: string; sourceUrl?: string | null } =
    $props();
  const parts = $derived(taskDescriptionParts(description, sourceUrl));
</script>

<div class="whitespace-pre-wrap break-words text-sm leading-7 text-muted [overflow-wrap:anywhere]">
  {#each parts as part, index (index)}
    {#if part.href}
      <!-- eslint-disable svelte/no-navigation-without-resolve -->
      <a
        href={part.href}
        target="_blank"
        rel="noopener noreferrer"
        title={part.text}
        class="inline-flex max-w-full items-center gap-1 rounded px-1 text-brand underline decoration-brand/30 underline-offset-4 hover:bg-brand/10 focus-visible:outline-2 focus-visible:outline-brand"
        >{part.label} <span aria-hidden="true">↗</span></a
      >
      <!-- eslint-enable svelte/no-navigation-without-resolve -->
    {:else}{part.text}{/if}
  {:else}No description provided.{/each}
</div>
