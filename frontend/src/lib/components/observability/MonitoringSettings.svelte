<script lang="ts">
  import { onMount } from 'svelte';
  import { getMonitoringSettings } from '$lib/services/observability';
  import { api } from '$lib/api';
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
      notice = 'Monitoring preferences saved.';
    } catch {
      error = 'Could not save monitoring preferences';
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
        if (!disposed) error = 'Monitoring settings unavailable';
      });
    return () => {
      disposed = true;
    };
  });
</script>

<section class="border-line rounded-xl border p-5">
  <h2>Observability & forecasts</h2>
  <p>
    Dashboard preferences apply immediately. Installing collectors and changing retention require a
    monitoring deployment restart. The monthly budget is an advisory display target.
  </p>
  {#if notice}<p role="status">{notice}</p>{/if}
  {#if settings}<form
      onsubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label
        ><input type="checkbox" bind:checked={settings.enabled} /> Enable infrastructure monitoring</label
      >
      <label
        ><input type="checkbox" bind:checked={settings.alertmanager_enabled} /> Enable alert ingestion</label
      >
      <label
        ><input type="checkbox" bind:checked={settings.forecasts_enabled} /> Enable statistical forecasts</label
      >
      <label
        >Metrics retention days<input
          type="number"
          min="1"
          max="90"
          bind:value={settings.retention_days}
        /></label
      >
      <label
        >Metrics maximum disk size<input
          bind:value={settings.retention_size}
          pattern="[1-9][0-9]*(MB|GB|TB)"
        /></label
      >
      <label
        >Live refresh seconds<input
          type="number"
          min="5"
          max="60"
          bind:value={settings.refresh_seconds}
        /></label
      >
      <label
        >CPU warning %<input
          type="number"
          min="1"
          max="100"
          bind:value={settings.cpu_warning}
        /></label
      >
      <label
        >RAM warning %<input
          type="number"
          min="1"
          max="100"
          bind:value={settings.ram_warning}
        /></label
      >
      <label
        >Disk warning %<input
          type="number"
          min="1"
          max="100"
          bind:value={settings.disk_warning}
        /></label
      >
      <label
        >Queue warning seconds<input
          type="number"
          min="30"
          max="86400"
          bind:value={settings.queue_warning_seconds}
        /></label
      >
      <label
        >Forecast minimum samples<input
          type="number"
          min="3"
          max="100"
          bind:value={settings.forecast_min_samples}
        /></label
      >
      <label
        >Default forecast days<input
          type="number"
          min="1"
          max="30"
          bind:value={settings.forecast_horizon_days}
        /></label
      >
      <label
        >Monthly AI budget USD<input
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
          placeholder="No target configured"
        /></label
      >
      <button disabled={saving}>{saving ? 'Saving…' : 'Save monitoring preferences'}</button>
    </form>{/if}
  {#if error}<p role="status">{error}</p>{/if}{#if settings}<dl>
      {#each Object.entries(settings) as [key, value] (key)}<div>
          <dt>{key.replaceAll('_', ' ')}</dt>
          <dd>{String(value)}</dd>
        </div>{/each}
    </dl>{/if}
</section>

<style>
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
  }
  input,
  button {
    border: 1px solid #64748b66;
    border-radius: 0.4rem;
    padding: 0.5rem;
    background: transparent;
  }
  input[type='checkbox'] {
    width: 1rem;
  }
  h2 {
    font-size: 1.1rem;
    margin-bottom: 0.5rem;
  }
  p {
    font-size: 0.85rem;
    opacity: 0.7;
  }
  dl {
    display: grid;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  dl div {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
  }
  dt {
    text-transform: capitalize;
  }
  dd {
    font-variant-numeric: tabular-nums;
  }
</style>
