<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { getTheme, setTheme, initTheme } from '$lib/theme.svelte';

  onMount(() => {
    initTheme();
  });

  function toggle() {
    setTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }
</script>

<button
  class="border-line text-muted hover:border-brand hover:text-brand grid size-9 place-items-center rounded-lg border transition-transform motion-safe:active:scale-90"
  onclick={toggle}
  aria-label={getTheme() === 'dark' ? t('theme.toLight') : t('theme.toDark')}
>
  {#key getTheme()}
    <svg
      class="size-4 motion-safe:animate-fade-in"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      {#if getTheme() === 'dark'}
        <circle cx="12" cy="12" r="4" />
        <path
          d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
        />
      {:else}
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
      {/if}
    </svg>
  {/key}
</button>
