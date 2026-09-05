<script lang="ts">
  import { getLocale, setLocale, initLocale, t, type Locale } from '$lib/i18n/index.svelte';
  import { onMount } from 'svelte';

  const locales: { value: Locale; label: string }[] = [
    { value: 'en', label: 'EN' },
    { value: 'ka', label: 'KA' }
  ];

  onMount(() => {
    initLocale();
  });

  function choose(next: Locale) {
    setLocale(next);
  }
</script>

<div class="border-line flex overflow-hidden rounded-lg border text-[10px] font-bold">
  {#each locales as option (option.value)}
    <button
      class="ease-smooth px-2 py-1.5 transition-colors {getLocale() === option.value
        ? 'bg-brand/15 text-brand'
        : 'text-muted hover:text-brand-2'}"
      onclick={() => choose(option.value)}
      aria-pressed={getLocale() === option.value}
      aria-label={`${t('nav.language')}: ${option.label}`}
    >
      {option.label}
    </button>
  {/each}
</div>
