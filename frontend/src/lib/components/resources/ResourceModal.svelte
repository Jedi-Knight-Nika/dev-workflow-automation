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
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  });
</script>

<div class="fixed inset-0 z-50 overflow-y-auto p-4 sm:p-8" role="presentation">
  <button
    type="button"
    class="fixed inset-0 cursor-default bg-black/55 backdrop-blur-sm"
    aria-label="Close dialog"
    onclick={onClose}
  ></button>

  <div
    class="bg-panel border-line relative mx-auto my-4 w-full max-w-2xl rounded-2xl border shadow-2xl sm:my-10"
    role="dialog"
    aria-modal="true"
    aria-labelledby="resource-modal-title"
  >
    <header class="border-line flex items-start justify-between gap-4 border-b p-5 sm:p-6">
      <div>
        <h2 id="resource-modal-title" class="text-xl font-semibold">{title}</h2>
        {#if description}<p class="text-muted mt-1 text-xs">{description}</p>{/if}
      </div>
      <button
        type="button"
        class="border-line shrink-0 rounded-lg border px-3 py-2 text-xs text-muted hover:border-brand hover:text-brand"
        onclick={onClose}
        aria-label="Close dialog"
      >
        Close
      </button>
    </header>

    <div class="p-5 sm:p-6">
      {@render children()}
    </div>
  </div>
</div>
