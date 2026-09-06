<script lang="ts">
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';

  let {
    title,
    description = '',
    onClose,
    children
  }: {
    title: string;
    description?: string;
    onClose: () => void;
    children: Snippet;
  } = $props();

  onMount(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  });
</script>

<div class="fixed inset-0 z-40 bg-black/45" role="presentation" onclick={onClose}></div>
<div
  class="bg-panel border-line fixed inset-y-0 right-0 z-50 w-full overflow-y-auto border-l p-5 shadow-2xl sm:max-w-xl"
  role="dialog"
  aria-modal="true"
  aria-label={title}
>
  <header class="border-line mb-5 flex items-start justify-between gap-4 border-b pb-4">
    <div>
      <h2 class="text-xl font-semibold">{title}</h2>
      {#if description}<p class="text-muted mt-1 text-xs">{description}</p>{/if}
    </div>
    <button
      type="button"
      class="border-line rounded-lg border px-3 py-2 text-xs text-muted hover:text-brand"
      onclick={onClose}
      aria-label="Close details"
    >
      Close
    </button>
  </header>
  {@render children()}
</div>
