<script lang="ts">
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
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
      message = 'Preferences saved.';
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
  eyebrow="Platform"
  title="Settings"
  description="Display preferences and platform-enforced execution boundaries."
/>
<main class="max-w-4xl space-y-6 p-4 sm:p-6 md:p-10">
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
        >Display name<input
          class="input mt-1 w-full"
          required
          bind:value={settings.general.display_name}
        /></label
      >
      <label
        >Timezone<input
          class="input mt-1 w-full"
          required
          placeholder="Asia/Tbilisi"
          bind:value={settings.general.timezone}
        /></label
      >
      <label
        >Date format<select class="input mt-1 w-full" bind:value={settings.general.date_format}
          >{#each ['YYYY-MM-DD', 'DD/MM/YYYY', 'MM/DD/YYYY'] as value (value)}<option
              >{value}</option
            >{/each}</select
        ></label
      >
      <label
        >Time format<select class="input mt-1 w-full" bind:value={settings.general.time_format}
          ><option>24H</option><option>12H</option></select
        ></label
      >
      <label
        >Landing page<select
          class="input mt-1 w-full"
          bind:value={settings.general.default_landing_page}
          ><option value="dashboard">Dashboard</option><option value="tasks">Tasks</option><option
            value="teams">Teams</option
          ></select
        ></label
      >
      <label
        >Task view<select class="input mt-1 w-full" bind:value={settings.general.default_task_view}
          ><option value="board">Board</option><option value="list">List</option></select
        ></label
      >
      <label
        >Appearance<select class="input mt-1 w-full" bind:value={settings.general.appearance}
          ><option value="system">System</option><option value="light">Light</option><option
            value="dark">Dark</option
          ></select
        ></label
      >
      <label class="flex items-center gap-2"
        ><input type="checkbox" bind:checked={settings.general.compact_dashboard} />Compact
        dashboard</label
      >
      <button class="btn-primary justify-self-start" disabled={saving}
        >{saving ? 'Saving…' : 'Save preferences'}</button
      >
    </form>
    <section class="border-line space-y-3 rounded-xl border p-5">
      <h2 class="font-semibold">Execution configuration</h2>
      <p class="text-muted">
        Configure native harnesses, models, optional roles, task and daily spending limits,
        validation commands and merge authority on <a class="text-brand" href={resolve('/teams')}
          >Teams</a
        >. Provider credentials belong to
        <a class="text-brand" href={resolve('/integrations')}>Integrations</a>.
      </p>
      <p class="text-sm">
        Developer feedback resumes the task's native session. Validation is deterministic and runs
        without network access or credentials. Git publication and merging are controlled platform
        operations.
      </p>
      <h3 class="font-medium">Locked safeguards</h3>
      <ul class="list-inside list-disc text-sm text-muted">
        {#each settings.security.locked_rules as rule (rule.key)}<li>
            {rule.key.replaceAll('_', ' ')}: {rule.effective_value}
          </li>{/each}
      </ul>
    </section>
  {:else if !error}<p>Loading preferences…</p>{/if}
</main>
