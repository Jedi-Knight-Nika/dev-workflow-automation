<script lang="ts">
  import { onMount } from 'svelte';
  import { getMonitoringSettings } from '$lib/services/observability';
  import { api } from '$lib/api';
  import { t } from '$lib/i18n/index.svelte';
  import type { MonitoringSettings } from '$lib/types/observability';
  let settings = $state<MonitoringSettings | null>(null);
  let error = $state('');
  let saving = $state(false),
    notice = $state('');
  async function save() {
    if (!settings) return;
    saving = true;
    error = '';
    try {
      settings = await api<MonitoringSettings>('/observability/settings', {
        method: 'PUT',
        body: JSON.stringify(settings)
      });
      notice = t('monitoring.saved');
    } catch {
      error = t('monitoring.saveFailed');
    } finally {
      saving = false;
    }
  }
  onMount(() => {
    let disposed = false;
    void getMonitoringSettings()
      .then((value) => {
        if (!disposed) settings = value;
      })
      .catch(() => {
        if (!disposed) error = t('monitoring.unavailable');
      });
    return () => {
      disposed = true;
    };
  });
</script>

<section class="panel">
  <h2>{t('monitoring.title')}</h2>
  <p>{t('monitoring.description')}</p>
  {#if notice}<p role="status" class="notice">{notice}</p>{/if}
  {#if settings}<form
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label class="checkbox"
        ><input type="checkbox" bind:checked={settings.enabled} />{t(
          'monitoring.enableMonitoring'
        )}</label
      >
      <label class="checkbox"
        ><input type="checkbox" bind:checked={settings.alertmanager_enabled} />{t(
          'monitoring.enableAlerts'
        )}</label
      >
      <label class="checkbox"
        ><input type="checkbox" bind:checked={settings.forecasts_enabled} />{t(
          'monitoring.enableForecasts'
        )}</label
      >
      <label
        >{t('monitoring.retentionDays')}<input
          class="input"
          type="number"
          min="1"
          max="90"
          bind:value={settings.retention_days}
        /></label
      >
      <label
        >{t('monitoring.retentionSize')}<input
          class="input"
          bind:value={settings.retention_size}
          pattern="[1-9][0-9]*(MB|GB|TB)"
        /></label
      >
      <label
        >{t('monitoring.refreshSeconds')}<input
          class="input"
          type="number"
          min="5"
          max="60"
          bind:value={settings.refresh_seconds}
        /></label
      >
      <label
        >{t('monitoring.cpuWarning')}<input
          class="input"
          type="number"
          min="1"
          max="100"
          bind:value={settings.cpu_warning}
        /></label
      >
      <label
        >{t('monitoring.ramWarning')}<input
          class="input"
          type="number"
          min="1"
          max="100"
          bind:value={settings.ram_warning}
        /></label
      >
      <label
        >{t('monitoring.diskWarning')}<input
          class="input"
          type="number"
          min="1"
          max="100"
          bind:value={settings.disk_warning}
        /></label
      >
      <label
        >{t('monitoring.queueWarning')}<input
          class="input"
          type="number"
          min="30"
          max="86400"
          bind:value={settings.queue_warning_seconds}
        /></label
      >
      <label
        >{t('monitoring.forecastMinSamples')}<input
          class="input"
          type="number"
          min="3"
          max="100"
          bind:value={settings.forecast_min_samples}
        /></label
      >
      <label
        >{t('monitoring.forecastHorizon')}<input
          class="input"
          type="number"
          min="1"
          max="30"
          bind:value={settings.forecast_horizon_days}
        /></label
      >
      <label
        >{t('monitoring.monthlyBudget')}<input
          class="input"
          type="number"
          min="0.01"
          step="0.01"
          value={settings.monthly_budget_usd ?? ''}
          onchange={(event) => {
            if (settings)
              settings.monthly_budget_usd = event.currentTarget.value
                ? Number(event.currentTarget.value)
                : null;
          }}
          placeholder={t('monitoring.noBudgetTarget')}
        /></label
      >
      <button class="btn-primary" disabled={saving}
        >{saving ? t('monitoring.saving') : t('monitoring.save')}</button
      >
    </form>{/if}
  {#if error}<p role="status" class="error">{error}</p>{/if}
</section>

<style>
  .panel {
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel);
    padding: 1.25rem;
  }
  h2 {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--color-heading);
    margin-bottom: 0.5rem;
  }
  p {
    font-size: 0.85rem;
    color: var(--color-muted);
  }
  .notice {
    color: var(--color-accent);
  }
  .error {
    color: var(--color-danger);
  }
  form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
    margin-block: 1rem;
  }
  label {
    display: grid;
    gap: 0.4rem;
    font-size: 0.85rem;
    color: var(--color-text);
  }
  label.checkbox {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }
  input[type='checkbox'] {
    width: 1rem;
    height: 1rem;
    accent-color: var(--color-brand);
  }
  button {
    justify-self: start;
  }
</style>
