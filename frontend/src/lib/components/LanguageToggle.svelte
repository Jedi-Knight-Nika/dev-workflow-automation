<script lang="ts">
  import { getLocale, setLocale, t, type Locale } from '$lib/i18n/index.svelte';

  const locales: { value: Locale; label: string }[] = [
    { value: 'en', label: 'EN' },
    { value: 'ka', label: 'KA' }
  ];

  function choose(next: Locale) {
    setLocale(next);
  }
</script>

<div class="border-line flex overflow-hidden rounded-lg border text-[10px] font-bold">
  {#each locales as option (option.value)}
    <button
      type="button"
      class="accent-action ease-smooth min-h-9 min-w-10 px-2 py-1.5 {getLocale() === option.value
        ? 'bg-brand text-on-brand'
        : 'text-muted hover:text-heading'}"
      onclick={() => choose(option.value)}
      aria-pressed={getLocale() === option.value}
      aria-label={`${t('nav.language')}: ${option.label}`}
    >
      {option.label}
    </button>
  {/each}
</div>
