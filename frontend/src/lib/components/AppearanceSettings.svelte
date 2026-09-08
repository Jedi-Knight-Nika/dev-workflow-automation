<script lang="ts">
  import { t } from '$lib/i18n/index.svelte';
  import { getTheme } from '$lib/theme.svelte';
  import LanguageToggle from './LanguageToggle.svelte';
  import ThemeToggle from './ThemeToggle.svelte';
</script>

<section class="border-line bg-panel rounded-2xl border p-5" aria-labelledby="appearance-title">
  <h2 id="appearance-title" class="text-heading text-lg font-bold">{t('appearance.title')}</h2>
  <p class="text-muted mt-2 text-sm">{t('appearance.description')}</p>
  <div class="mt-5 grid gap-4 sm:grid-cols-2">
    <div
      class="border-line bg-panel-alt flex items-center justify-between gap-4 rounded-xl border p-4"
    >
      <div>
        <p class="text-heading text-sm font-semibold">{t('nav.theme')}</p>
        <p class="text-muted mt-1 text-xs">
          {getTheme() === 'dark'
            ? t('settingsPage.appearanceDark')
            : t('settingsPage.appearanceLight')}
        </p>
      </div>
      <ThemeToggle />
    </div>
    <div
      class="border-line bg-panel-alt flex items-center justify-between gap-4 rounded-xl border p-4"
    >
      <p class="text-heading text-sm font-semibold">{t('nav.language')}</p>
      <LanguageToggle />
    </div>
  </div>
</section>
