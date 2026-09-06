<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import type { AccountSettings, TelegramStatus } from '$lib/types';
  import {
    configureTelegram,
    connectTelegram,
    disconnectTelegram,
    telegramStatus,
    testTelegram
  } from '$lib/services/notifications';
  import {
    getAccountSettings,
    updateAccountSettings,
    type SettingsSection
  } from '$lib/services/settings';

  type PageSection = SettingsSection | 'notifications' | 'security';
  const sections: Array<{ id: PageSection; label: string; description: string }> = [
    { id: 'general', label: 'General', description: 'Display and regional preferences' },
    { id: 'ai', label: 'AI defaults', description: 'Defaults inherited by new agents' },
    { id: 'execution', label: 'Execution', description: 'Default worker behavior' },
    { id: 'safety', label: 'Safety & approvals', description: 'Default authority boundaries' },
    { id: 'notifications', label: 'Notifications', description: 'Telegram critical alerting' },
    { id: 'knowledge', label: 'Knowledge & RAG', description: 'Repository indexing defaults' },
    { id: 'storage', label: 'Storage & retention', description: 'Cleanup and spending limits' },
    { id: 'security', label: 'Security', description: 'Platform-enforced protections' }
  ];

  let selected = $state<PageSection>('general');
  let settings = $state<AccountSettings | null>(null);
  let baseline = $state('');
  let loading = $state(true);
  let saving = $state(false);
  let message = $state('');
  let telegram = $state<TelegramStatus | null>(null);
  let botToken = $state('');
  let webhookBaseUrl = $state('');
  let editingBot = $state(false);

  const editable = $derived(selected !== 'notifications' && selected !== 'security');
  const dirty = $derived(
    settings !== null &&
      editable &&
      JSON.stringify(settings[selected as SettingsSection]) !== baseline
  );

  function rememberSection() {
    if (settings && editable) baseline = JSON.stringify(settings[selected as SettingsSection]);
  }
  function choose(section: PageSection) {
    selected = section;
    message = '';
    rememberSection();
  }
  async function load() {
    loading = true;
    try {
      [settings, telegram] = await Promise.all([getAccountSettings(), telegramStatus()]);
      rememberSection();
    } catch (cause) {
      message = cause instanceof Error ? cause.message : String(cause);
    } finally {
      loading = false;
    }
  }
  async function save() {
    if (!settings || !editable) return;
    saving = true;
    try {
      const section = selected as SettingsSection;
      settings = await updateAccountSettings(section, settings[section]);
      rememberSection();
      message = 'Settings saved.';
    } catch (cause) {
      message = cause instanceof Error ? cause.message : String(cause);
    } finally {
      saving = false;
    }
  }
  function discard() {
    if (!settings || !editable || !baseline) return;
    const section = selected as SettingsSection;
    settings[section] = JSON.parse(baseline) as never;
  }
  async function configure() {
    saving = true;
    try {
      telegram = await configureTelegram(botToken, webhookBaseUrl);
      botToken = '';
      editingBot = false;
      message = 'Bot verified and encrypted. Connect your Telegram account next.';
    } catch (cause) {
      message = cause instanceof Error ? cause.message : String(cause);
    } finally {
      saving = false;
    }
  }
  async function connect() {
    const result = await connectTelegram();
    window.open(result.connect_url, '_blank', 'noopener,noreferrer');
    message = 'Press Start in Telegram, then refresh status.';
  }
  onMount(() => void load());
</script>

<PageHeader
  eyebrow="Platform"
  title="Settings"
  description="Global defaults and platform behavior. Team, Role, Agent, Repository, and Integration configuration stays in its own domain."
/>

<main class="p-4 sm:p-6 md:p-10">
  {#if loading}
    <div class="grid gap-6 lg:grid-cols-[260px_minmax(0,760px)]" aria-busy="true">
      <Skeleton class="h-[420px] rounded-xl" /><Skeleton class="h-[520px] rounded-xl" />
    </div>
  {:else if settings}
    <div class="grid items-start gap-6 lg:grid-cols-[260px_minmax(0,760px)]">
      <nav
        class="border-line bg-panel overflow-hidden rounded-xl border"
        aria-label="Settings sections"
      >
        {#each sections as section (section.id)}
          <button
            class="border-line hover:bg-panel-alt block w-full border-b px-4 py-3 text-left transition-colors last:border-0 {selected ===
            section.id
              ? 'bg-panel-alt'
              : ''}"
            onclick={() => choose(section.id)}
          >
            <strong class="text-heading block text-sm">{section.label}</strong><span
              class="text-muted mt-0.5 block text-xs">{section.description}</span
            >
          </button>
        {/each}
      </nav>

      <section class="border-line bg-panel overflow-hidden rounded-xl border">
        <header class="border-line border-b p-5">
          <h2 class="text-heading text-lg font-semibold">
            {sections.find((item) => item.id === selected)?.label}
          </h2>
          <p class="text-muted mt-1 text-sm">
            {sections.find((item) => item.id === selected)?.description}
          </p>
        </header>

        {#if selected === 'general'}
          <div class="grid gap-5 p-5 sm:grid-cols-2">
            <label class="setting-field sm:col-span-2"
              >Display name<input bind:value={settings.general.display_name} /></label
            >
            <label class="setting-field"
              >Timezone<input
                bind:value={settings.general.timezone}
                placeholder="Asia/Tbilisi"
              /></label
            >
            <label class="setting-field"
              >Date format<select bind:value={settings.general.date_format}
                ><option>YYYY-MM-DD</option><option>DD/MM/YYYY</option><option>MM/DD/YYYY</option
                ></select
              ></label
            >
            <label class="setting-field"
              >Time format<select bind:value={settings.general.time_format}
                ><option value="24H">24-hour</option><option value="12H">12-hour</option></select
              ></label
            >
            <label class="setting-field"
              >Landing page<select bind:value={settings.general.default_landing_page}
                ><option value="dashboard">Dashboard</option><option value="tasks">Tasks</option
                ><option value="teams">Teams</option></select
              ></label
            >
            <label class="setting-field"
              >Task view<select bind:value={settings.general.default_task_view}
                ><option value="board">Board</option><option value="list">List</option></select
              ></label
            >
            <label class="setting-field"
              >Appearance<select bind:value={settings.general.appearance}
                ><option value="system">System</option><option value="light">Light</option><option
                  value="dark">Dark</option
                ></select
              ></label
            >
            <label class="toggle-row sm:col-span-2"
              ><input type="checkbox" bind:checked={settings.general.compact_dashboard} /><span
                ><strong>Compact dashboard</strong><small
                  >Reduce spacing in operational views.</small
                ></span
              ></label
            >
          </div>
        {:else if selected === 'ai'}
          <div class="grid gap-5 p-5 sm:grid-cols-2">
            <label class="setting-field"
              >Default provider<input
                bind:value={settings.ai.default_provider_id}
                placeholder="openai"
              /></label
            >
            <label class="setting-field"
              >Default model<input
                bind:value={settings.ai.default_model}
                placeholder="Provider default"
              /></label
            >
            <label class="setting-field"
              >Reasoning<select bind:value={settings.ai.default_reasoning_level}
                ><option value="default">Provider default</option><option value="low">Low</option
                ><option value="medium">Medium</option><option value="high">High</option><option
                  value="max">Maximum</option
                ></select
              ></label
            >
            <label class="setting-field"
              >Max output tokens<input
                type="number"
                min="256"
                bind:value={settings.ai.default_max_output_tokens}
                placeholder="Provider default"
              /></label
            >
            <div class="locked-row">
              <span
                ><strong>Provider failure</strong><small
                  >Fallback routing is not enabled for this installation.</small
                ></span
              ><code>PAUSE AND NOTIFY</code>
            </div>
            <label class="setting-field"
              >Output retries<input
                type="number"
                min="0"
                max="10"
                bind:value={settings.ai.structured_output_retry_limit}
              /></label
            >
            <p class="info-box sm:col-span-2">
              Explicit Team, Role, and Agent configuration remains authoritative.
            </p>
          </div>
        {:else if selected === 'execution'}
          <div class="grid gap-5 p-5 sm:grid-cols-2">
            <label class="setting-field"
              >Execution mode<select bind:value={settings.execution.default_execution_mode}
                ><option value="AUTONOMOUS">Autonomous</option><option value="CONSERVATIVE"
                  >Conservative</option
                ><option value="CUSTOM">Custom</option></select
              ></label
            >
            <label class="setting-field"
              >Job timeout (seconds)<input
                type="number"
                min="60"
                max="86400"
                bind:value={settings.execution.default_job_timeout_seconds}
              /></label
            >
            <div class="locked-row sm:col-span-2">
              <span
                ><strong>Worker runtime</strong><small
                  >Host-managed; restart required to change.</small
                ></span
              ><code>{settings.execution.default_worker_runtime} 🔒</code>
            </div>
            <div class="locked-row sm:col-span-2">
              <span
                ><strong>Scheduler concurrency</strong><small>Host-managed operational limit.</small
                ></span
              ><code>{settings.execution.max_concurrent_workers} 🔒</code>
            </div>
          </div>
        {:else if selected === 'safety'}
          <div class="space-y-5 p-5">
            <label class="setting-field"
              >Merge PR<select bind:value={settings.safety.default_merge_policy}
                ><option value="REQUIRE_HUMAN">Require human</option><option value="DENY"
                  >Deny</option
                ></select
              ></label
            >
            <div class="locked-row">
              <span
                ><strong>Unknown network</strong><small
                  >Only package registries and approved hosts may be reached.</small
                ></span
              ><code>DENY 🔒</code>
            </div>
            <label class="setting-field"
              >Dependency installation<select
                bind:value={settings.safety.default_dependency_install_policy}
                ><option value="ALLOW">Allow in sandbox</option><option value="REQUIRE_HUMAN"
                  >Require human</option
                ><option value="DENY">Deny</option></select
              ></label
            >
            <label class="setting-field"
              >Push task branch<select bind:value={settings.safety.default_push_task_branch_policy}
                ><option value="ALLOW">Allow</option><option value="REQUIRE_HUMAN"
                  >Require human</option
                ><option value="DENY">Deny</option></select
              ></label
            >
            <p class="info-box">
              Platform hard-denies always win. Existing Team overrides are unchanged.
            </p>
          </div>
        {:else if selected === 'knowledge'}
          <div class="space-y-3 p-5">
            <label class="setting-field mb-5"
              >Context strategy<select bind:value={settings.knowledge.context_strategy}
                ><option value="MINIMAL">Minimal</option><option value="BALANCED">Balanced</option
                ><option value="DEEP">Deep</option></select
              ></label
            >
            <label class="toggle-row"
              ><input
                type="checkbox"
                bind:checked={settings.knowledge.auto_index_repositories}
              /><span><strong>Index repositories after connection</strong></span></label
            >
            <label class="toggle-row"
              ><input
                type="checkbox"
                bind:checked={settings.knowledge.incremental_index_after_merge}
              /><span><strong>Incrementally index after merge</strong></span></label
            >
            <label class="toggle-row"
              ><input type="checkbox" bind:checked={settings.knowledge.index_source_code} /><span
                ><strong>Index source code</strong></span
              ></label
            >
            <label class="toggle-row"
              ><input type="checkbox" bind:checked={settings.knowledge.index_tests} /><span
                ><strong>Index tests</strong></span
              ></label
            >
            <label class="toggle-row"
              ><input type="checkbox" bind:checked={settings.knowledge.index_documentation} /><span
                ><strong>Index documentation</strong></span
              ></label
            >
            <label class="toggle-row"
              ><input
                type="checkbox"
                bind:checked={settings.knowledge.ignore_generated_files}
              /><span><strong>Ignore generated files</strong></span></label
            >
          </div>
        {:else if selected === 'storage'}
          <div class="grid gap-5 p-5 sm:grid-cols-2">
            <label class="setting-field"
              >Completed workspaces (days)<input
                type="number"
                min="1"
                bind:value={settings.storage.completed_workspace_retention_days}
              /></label
            >
            <label class="setting-field"
              >Failed workspaces (days)<input
                type="number"
                min="1"
                bind:value={settings.storage.failed_workspace_retention_days}
              /></label
            >
            <label class="setting-field"
              >Monthly hard stop (USD)<input
                type="number"
                min="0"
                step="0.01"
                bind:value={settings.storage.monthly_cost_hard_stop}
                placeholder="Disabled"
              /></label
            >
            <p class="info-box sm:col-span-2">
              Cleanup never removes active, leased, dirty, or unmanaged worktrees.
            </p>
          </div>
        {:else if selected === 'notifications'}
          <div class="space-y-4 p-5">
            <div class="locked-row">
              <span
                ><strong>In-app notifications</strong><small>System activity remains visible.</small
                ></span
              ><code>ENABLED</code>
            </div>
            <div class="locked-row">
              <span
                ><strong>Telegram critical alerts</strong><small
                  >Action-required and critical only.</small
                ></span
              ><code
                >{telegram?.connected
                  ? 'CONNECTED'
                  : telegram?.configured
                    ? 'CONFIGURED'
                    : 'NOT SET'}</code
              >
            </div>
            {#if !telegram?.configured || editingBot}
              <form
                class="space-y-3"
                onsubmit={(event) => {
                  event.preventDefault();
                  void configure();
                }}
              >
                <label class="setting-field"
                  >Bot token<input
                    type="password"
                    bind:value={botToken}
                    required
                    autocomplete="off"
                  /></label
                >
                <label class="setting-field"
                  >Public HTTPS backend URL<input
                    type="url"
                    bind:value={webhookBaseUrl}
                    placeholder="https://api.example.com"
                  /></label
                >
                <div class="flex gap-2">
                  <button class="primary-button" disabled={saving}
                    >{saving ? 'Verifying…' : 'Verify and save'}</button
                  >{#if telegram?.configured}<button
                      type="button"
                      class="secondary-button"
                      onclick={() => (editingBot = false)}>Cancel</button
                    >{/if}
                </div>
              </form>
            {:else}
              <div class="flex flex-wrap gap-2">
                {#if !telegram.connected}<button
                    class="primary-button"
                    disabled={!telegram.webhook_configured}
                    onclick={() => void connect()}>Connect Telegram</button
                  >{/if}
                {#if telegram.connected}<button
                    class="secondary-button"
                    onclick={async () => {
                      await testTelegram();
                      message = 'Test notification queued.';
                    }}>Send test</button
                  ><button
                    class="danger-button"
                    onclick={async () => {
                      await disconnectTelegram();
                      telegram = await telegramStatus();
                    }}>Disconnect</button
                  >{/if}
                <button
                  class="secondary-button"
                  onclick={async () => (telegram = await telegramStatus())}>Refresh</button
                ><button class="secondary-button" onclick={() => (editingBot = true)}
                  >Replace bot</button
                >
              </div>
            {/if}
          </div>
        {:else if selected === 'security'}
          <div class="space-y-3 p-5">
            <div class="locked-row">
              <span
                ><strong>Secret masking</strong><small>Secrets are removed from outputs.</small
                ></span
              ><code>ENABLED 🔒</code>
            </div>
            <div class="locked-row">
              <span
                ><strong>Fresh session per job</strong><small
                  >Task memory persists outside provider sessions.</small
                ></span
              ><code>ENABLED 🔒</code>
            </div>
            {#each settings.security.locked_rules as rule (rule.key)}<div class="locked-row">
                <span
                  ><strong>{rule.key.replaceAll('_', ' ')}</strong><small
                    >Platform security rule</small
                  ></span
                ><code>{rule.effective_value} 🔒</code>
              </div>{/each}
          </div>
        {/if}

        {#if editable}<footer
            class="border-line bg-panel-alt flex min-h-16 items-center justify-between gap-4 border-t px-5 py-3"
          >
            <span class="text-muted text-xs"
              >Version {settings.settings_version}{dirty ? ' · Unsaved changes' : ''}</span
            >
            <div class="flex gap-2">
              <button class="secondary-button" disabled={!dirty || saving} onclick={discard}
                >Discard</button
              ><button
                class="primary-button"
                disabled={!dirty || saving}
                onclick={() => void save()}
                >{#if saving}<Spinner class="size-3.5" />{/if} Save</button
              >
            </div>
          </footer>{/if}
        {#if message}<p class="border-line text-muted border-t px-5 py-3 text-xs">{message}</p>{/if}
      </section>
    </div>
  {:else}<p class="text-danger">{message || 'Settings could not be loaded.'}</p>{/if}
</main>

<style>
  :global(.setting-field) {
    display: grid;
    gap: 0.4rem;
    color: var(--color-muted);
    font-size: 0.75rem;
  }
  :global(.setting-field input),
  :global(.setting-field select) {
    width: 100%;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    color: var(--color-heading);
    padding: 0.6rem 0.75rem;
    font-size: 0.875rem;
  }
  :global(.toggle-row),
  :global(.locked-row) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    padding: 0.8rem 0.9rem;
  }
  :global(.toggle-row) {
    justify-content: flex-start;
    cursor: pointer;
  }
  :global(.toggle-row input) {
    accent-color: var(--color-brand);
  }
  :global(.toggle-row span),
  :global(.locked-row span) {
    display: grid;
    gap: 0.15rem;
  }
  :global(.toggle-row strong),
  :global(.locked-row strong) {
    color: var(--color-heading);
    font-size: 0.82rem;
    text-transform: capitalize;
  }
  :global(.toggle-row small),
  :global(.locked-row small) {
    color: var(--color-muted);
    font-size: 0.72rem;
  }
  :global(.locked-row code) {
    color: var(--color-muted);
    font-size: 0.72rem;
    white-space: nowrap;
  }
  :global(.info-box) {
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    background: var(--color-panel-alt);
    color: var(--color-muted);
    padding: 0.8rem;
    font-size: 0.75rem;
  }
  :global(.primary-button),
  :global(.secondary-button),
  :global(.danger-button) {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    border-radius: 0.5rem;
    padding: 0.55rem 0.9rem;
    font-size: 0.8rem;
  }
  :global(.primary-button) {
    background: var(--color-brand);
    color: white;
  }
  :global(.secondary-button) {
    border: 1px solid var(--color-line);
  }
  :global(.danger-button) {
    border: 1px solid var(--color-danger);
    color: var(--color-danger);
  }
  :global(button:disabled) {
    cursor: not-allowed;
    opacity: 0.45;
  }
</style>
