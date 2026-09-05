<script lang="ts">
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { t } from '$lib/i18n/index.svelte';
</script>

<PageHeader
  eyebrow={t('settings.eyebrow')}
  title={t('settings.title')}
  description={t('settings.description')}
/>
<main class="p-4 sm:p-6 md:p-10">
  <section class="border-line max-w-2xl overflow-hidden rounded-xl border">
    <div class="border-line flex justify-between border-b p-5">
      <div>
        <strong>{t('settings.executionLane')}</strong>
        <p class="text-muted text-xs">{t('settings.executionLaneDescription')}</p>
      </div>
      <span class="font-mono text-sm">1</span>
    </div>
    <div class="border-line flex justify-between border-b p-5">
      <div>
        <strong>{t('settings.mergePolicy')}</strong>
        <p class="text-muted text-xs">{t('settings.mergePolicyDescription')}</p>
      </div>
      <span class="font-mono text-sm">{t('settings.manual')}</span>
    </div>
    <div class="flex justify-between p-5">
      <div>
        <strong>{t('settings.workerTimeout')}</strong>
        <p class="text-muted text-xs">{t('settings.workerTimeoutDescription')}</p>
      </div>
      <span class="font-mono text-sm">300s</span>
    </div>
  </section>
</main>
