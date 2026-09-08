<script lang="ts">
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import MonitoringSettings from '$lib/components/observability/MonitoringSettings.svelte';
  import ObserverSettings from '$lib/observer/ObserverSettings.svelte';
  import AccentPicker from '$lib/components/AccentPicker.svelte';
  import FontSizePicker from '$lib/components/FontSizePicker.svelte';
  import DisplayModePicker from '$lib/components/DisplayModePicker.svelte';
  import AppearanceSettings from '$lib/components/AppearanceSettings.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { getAccountSettings, updateAccountSettings } from '$lib/services/settings';
  import type { AccountSettings } from '$lib/types';
  let settings = $state<AccountSettings | null>(null),
    error = $state(''),
    message = $state(''),
    saving = $state(false);
  async function load() {
    try {
      settings = await getAccountSettings();
    } catch (cause) {
      error = String(cause);
    }
  }
  async function save() {
    if (!settings || saving) return;
    saving = true;
    error = '';
    message = '';
    try {
      settings = await updateAccountSettings('general', settings.general);
      message = t('settingsPage.preferencesSaved');
    } catch (cause) {
      error = String(cause);
    } finally {
      saving = false;
    }
  }
  onMount(() => {
    void load();
  });
</script>

<PageHeader
  eyebrow={t('settingsPage.eyebrow')}
  title={t('settingsPage.title')}
  description={t('settingsPage.description')}
/>
<main class="max-w-4xl space-y-6 p-4 sm:p-6 md:p-10">
  <AppearanceSettings />
  <DisplayModePicker />
  <AccentPicker />
  <FontSizePicker />
  <MonitoringSettings />
  <ObserverSettings />
  {#if error}<ErrorBanner message={error} />{/if}
  {#if message}<p role="status" class="text-accent">{message}</p>{/if}
  {#if settings}
    <form
      class="border-line grid gap-4 rounded-xl border p-5 sm:grid-cols-2"
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label
        >{t('settingsPage.displayName')}<input
          class="input mt-1 w-full"
          required
          bind:value={settings.general.display_name}
        /></label
      >
      <label
        >{t('settingsPage.timezone')}<input
          class="input mt-1 w-full"
          required
          placeholder="Asia/Tbilisi"
          bind:value={settings.general.timezone}
        /></label
      >
      <label
        >{t('settingsPage.dateFormat')}<select
          class="input mt-1 w-full"
          bind:value={settings.general.date_format}
          >{#each ['YYYY-MM-DD', 'DD/MM/YYYY', 'MM/DD/YYYY'] as value (value)}<option
              >{value}</option
            >{/each}</select
        ></label
      >
      <label
        >{t('settingsPage.timeFormat')}<select
          class="input mt-1 w-full"
          bind:value={settings.general.time_format}><option>24H</option><option>12H</option></select
        ></label
      >
      <label
        >{t('settingsPage.landingPage')}<select
          class="input mt-1 w-full"
          bind:value={settings.general.default_landing_page}
          ><option value="dashboard">{t('nav.dashboard')}</option><option value="tasks"
            >{t('nav.tasks')}</option
          ><option value="teams">{t('nav.teams')}</option></select
        ></label
      >
      <label
        >{t('settingsPage.taskView')}<select
          class="input mt-1 w-full"
          bind:value={settings.general.default_task_view}
          ><option value="board">{t('settingsPage.taskViewBoard')}</option><option value="list"
            >{t('settingsPage.taskViewList')}</option
          ></select
        ></label
      >
      <label class="flex items-center gap-2"
        ><input type="checkbox" bind:checked={settings.general.compact_dashboard} />{t(
          'settingsPage.compactDashboard'
        )}</label
      >
      <button class="btn-primary justify-self-start" disabled={saving}
        >{saving ? t('settingsPage.saving') : t('settingsPage.savePreferences')}</button
      >
    </form>
    <section class="border-line space-y-3 rounded-xl border p-5">
      <h2 class="font-semibold">{t('settingsPage.executionConfiguration')}</h2>
      <p class="text-muted">
        {t('settingsPage.executionConfigIntroBefore')}
        <a class="text-brand" href={resolve('/teams')}>{t('nav.teams')}</a>{t(
          'settingsPage.executionConfigIntroMid'
        )}
        <a class="text-brand" href={resolve('/integrations')}>{t('nav.integrations')}</a>{t(
          'settingsPage.executionConfigIntroTail'
        )}
      </p>
      <p class="text-sm">
        {t('settingsPage.executionConfigDetail')}
      </p>
      <h3 class="font-medium">{t('settingsPage.lockedSafeguards')}</h3>
      <ul class="list-inside list-disc text-sm text-muted">
        {#each settings.security.locked_rules as rule (rule.key)}<li>
            {rule.key.replaceAll('_', ' ')}: {rule.effective_value}
          </li>{/each}
      </ul>
    </section>
  {:else if !error}<p>{t('settingsPage.loadingPreferences')}</p>{/if}
</main>
