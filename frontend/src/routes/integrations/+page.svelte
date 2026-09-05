<script lang="ts">
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import {
    saveIntegration,
    testIntegration,
    getGithubAppInstallUrl,
    getGithubInstallationAccount,
    listLinearWorkflowStates
  } from '$lib/services/integrations';
  import { integrationsResource, webhookHealthResource } from '$lib/stores/integrations.svelte';
  import { repositoriesResource } from '$lib/stores/repositories.svelte';
  import LinearWorkflowFields from '$lib/components/integrations/LinearWorkflowFields.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import type { GitHubInstallationAccount, LinearWorkflowState } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';
  const providers = [
    { name: 'github', type: 'source_control', label: 'GitHub', active: true },
    { name: 'linear', type: 'task_management', label: 'Linear', active: true },
    { name: 'openai', type: 'ai', label: 'OpenAI', active: true },
    { name: 'anthropic', type: 'ai', label: 'Anthropic', active: true },
    { name: 'google', type: 'ai', label: 'Google', active: true },
    { name: 'npm_registry', type: 'package_registry', label: 'npm Registry', active: true },
    { name: 'pypi_registry', type: 'package_registry', label: 'PyPI Registry', active: true },
    { name: 'gitlab', type: 'source_control', label: 'GitLab', active: false },
    { name: 'jira', type: 'task_management', label: 'Jira', active: false }
  ];
  let error = '';
  let editing = '';
  let credential = '';
  let saving = false;
  let triggerLabel = 'AI Ready';
  let repositoryId = '';
  let todoStateId = '';
  let inProgressStateId = '';
  let inReviewStateId = '';
  let blockedStateId = '';
  let readyForTestingStateId = '';
  let doneStateId = '';
  let linearStates: LinearWorkflowState[] = [];
  let loadingLinearStates = false;
  let refreshingStatuses = false;
  let statusesRefreshedAt: Date | null = null;
  let registryUrl = '';
  let githubAccount: GitHubInstallationAccount | null = null;
  async function loadGithubAccount() {
    try {
      githubAccount = await getGithubInstallationAccount();
    } catch {
      githubAccount = null;
    }
  }
  async function installGithubApp() {
    error = '';
    try {
      const result = await getGithubAppInstallUrl();
      window.location.assign(result.url);
    } catch (cause) {
      error = String(cause);
    }
  }
  onMount(() => {
    integrationsResource.load();
    webhookHealthResource.load();
    repositoriesResource.load();
    loadGithubAccount();
  });
  function status(name: string) {
    return (
      integrationsResource.data.find((item) => item.provider_name === name)?.status ||
      'DISCONNECTED'
    );
  }
  function integration(name: string) {
    return integrationsResource.data.find((item) => item.provider_name === name);
  }
  function deliveryHealth(name: string) {
    return webhookHealthResource.data.find((item) => item.provider === name);
  }
  async function save(provider: (typeof providers)[number]) {
    saving = true;
    error = '';
    try {
      await saveIntegration(provider.name, {
        provider_type: provider.type,
        status: 'CONFIGURED',
        configuration:
          provider.name === 'linear'
            ? {
                trigger_label: triggerLabel,
                repository_id: repositoryId || null,
                todo_state_id: todoStateId || null,
                in_progress_state_id: inProgressStateId || null,
                in_review_state_id: inReviewStateId || null,
                blocked_state_id: blockedStateId || null,
                ready_for_testing_state_id: readyForTestingStateId || null,
                done_state_id: doneStateId || null
              }
            : provider.name === 'npm_registry'
              ? { registry_url: registryUrl || null }
              : provider.name === 'pypi_registry'
                ? { index_url: registryUrl || null }
                : {},
        credential: credential || null
      });
      await testIntegration(provider.name);
      credential = '';
      editing = '';
      await integrationsResource.refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      saving = false;
    }
  }

  async function discoverLinearStates() {
    loadingLinearStates = true;
    error = '';
    try {
      linearStates = await listLinearWorkflowStates();
      if (!todoStateId) {
        todoStateId = linearStates.find((state) => state.name.toLowerCase() === 'todo')?.id || '';
      }
      if (!inProgressStateId) {
        inProgressStateId =
          linearStates.find((state) => state.name.toLowerCase() === 'in progress')?.id || '';
      }
      if (!inReviewStateId) {
        inReviewStateId =
          linearStates.find((state) => state.name.toLowerCase() === 'in review')?.id || '';
      }
      if (!readyForTestingStateId) {
        readyForTestingStateId =
          linearStates.find((state) => state.name.toLowerCase() === 'ready for testing')?.id || '';
      }
      if (!blockedStateId) {
        blockedStateId =
          linearStates.find((state) => state.name.toLowerCase() === 'blocked')?.id || '';
      }
      if (!doneStateId) {
        doneStateId = linearStates.find((state) => state.name.toLowerCase() === 'done')?.id || '';
      }
    } catch (cause) {
      error = String(cause);
    } finally {
      loadingLinearStates = false;
    }
  }
  async function refreshStatuses() {
    refreshingStatuses = true;
    error = '';
    try {
      const configured = integrationsResource.data.filter((item) => item.has_credentials);
      const results = await Promise.allSettled(
        configured.map((item) => testIntegration(item.provider_name))
      );
      await Promise.all([
        integrationsResource.refresh(),
        webhookHealthResource.refresh(),
        loadGithubAccount()
      ]);
      statusesRefreshedAt = new Date();
      const rejected = results.filter((result) => result.status === 'rejected');
      if (rejected.length)
        error = t('integrations.connectionChecksIncomplete', { count: rejected.length });
    } finally {
      refreshingStatuses = false;
    }
  }
</script>

<PageHeader
  eyebrow={t('integrations.eyebrow')}
  title={t('integrations.title')}
  description={t('integrations.description')}
/>
<main class="p-4 sm:p-6 md:p-10">
  <ErrorBanner
    message={error || integrationsResource.error || webhookHealthResource.error}
    class="mb-4"
  />
  <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <p class="text-muted text-xs">
      {t('integrations.autoTestedHint')}
      {#if statusesRefreshedAt}
        {t('integrations.lastRefreshed', { time: statusesRefreshedAt.toLocaleTimeString() })}
      {/if}
    </p>
    <Button onclick={refreshStatuses} disabled={refreshingStatuses}>
      {refreshingStatuses
        ? t('integrations.checkingConnections')
        : t('integrations.refreshStatuses')}
    </Button>
  </div>
  <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
    {#each providers as provider, index (provider.name)}<article
        class="border-line bg-panel rounded-xl border p-5 card-hover motion-safe:animate-fade-in-up"
        style="animation-delay: {index * 40}ms"
      >
        <p class="text-muted font-mono text-[10px] tracking-widest uppercase">
          {provider.type.replaceAll('_', ' ')}
        </p>
        <h2 class="my-2 text-xl font-semibold">{provider.label}</h2>
        {#if provider.name === 'github'}
          <p class="text-muted mb-3 text-xs">
            {t('integrations.githubAuthHint')}
          </p>
          {#if githubAccount}
            <button
              type="button"
              class="border-line bg-panel-alt mb-3 flex items-center gap-3 rounded-lg border p-3 hover:border-brand"
              onclick={() =>
                window.open(githubAccount?.profile_url, '_blank', 'noopener,noreferrer')}
            >
              <img class="h-9 w-9 rounded-full" src={githubAccount.avatar_url} alt="" />
              <span>
                <strong class="block text-sm">@{githubAccount.login}</strong>
                <span class="text-muted text-[10px]"
                  >{t('integrations.accountType', { type: githubAccount.account_type })}</span
                >
              </span>
            </button>
          {/if}
        {/if}
        {#if deliveryHealth(provider.name)}
          {@const health = deliveryHealth(provider.name)!}
          <div
            class="border-line mb-3 grid grid-cols-2 overflow-hidden rounded-lg border font-mono text-[10px]"
          >
            <span class="border-line border-r p-2"
              >{t('integrations.webhookPending')} {health.pending}</span
            >
            <span class="p-2 {health.failed ? 'text-danger' : 'text-accent'}"
              >{t('integrations.failed')} {health.failed}</span
            >
          </div>
          {#if health.last_error}
            <p class="mb-3 text-xs text-danger">
              {t('integrations.lastDeliveryError')}: {health.last_error}
            </p>
          {/if}
        {/if}
        {#if editing === provider.name && provider.name !== 'github'}
          <form
            class="mt-4"
            onsubmit={(event) => {
              event.preventDefault();
              save(provider);
            }}
          >
            <TextField
              id={`credential-${provider.name}`}
              label={`${t('integrations.apiKeyOrToken')} ${
                integrationsResource.data.find((item) => item.provider_name === provider.name)
                  ?.has_credentials
                  ? t('integrations.keepExisting')
                  : ''
              }`}
              type="password"
              bind:value={credential}
              autocomplete="off"
              required={!integrationsResource.data.find(
                (item) => item.provider_name === provider.name
              )?.has_credentials}
            />
            {#if provider.name === 'linear'}
              <LinearWorkflowFields
                bind:triggerLabel
                bind:repositoryId
                bind:todoStateId
                bind:inProgressStateId
                bind:inReviewStateId
                bind:blockedStateId
                bind:readyForTestingStateId
                bind:doneStateId
                repositories={repositoriesResource.data}
                {linearStates}
                {loadingLinearStates}
                hasCredentials={!!integrationsResource.data.find(
                  (item) => item.provider_name === 'linear'
                )?.has_credentials}
                onDiscoverStates={discoverLinearStates}
              />
            {/if}
            {#if provider.name === 'npm_registry' || provider.name === 'pypi_registry'}
              <TextField
                id={`registry-url-${provider.name}`}
                label={provider.name === 'npm_registry'
                  ? t('integrations.registryUrl')
                  : t('integrations.packageIndexUrl')}
                type="url"
                bind:value={registryUrl}
                placeholder={provider.name === 'npm_registry'
                  ? 'https://npm.pkg.github.com'
                  : 'https://pypi.example.com/simple'}
                class="mt-3"
              />
            {/if}
            <p class="text-muted mt-2 text-[10px]">
              {t('integrations.storedEncrypted')}
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Button variant="primary" type="submit" disabled={saving}
                >{saving ? t('integrations.saving') : t('integrations.saveSecurely')}</Button
              >
              <Button
                type="button"
                onclick={() => {
                  editing = '';
                  credential = '';
                }}>{t('integrations.cancel')}</Button
              >
            </div>
          </form>
        {/if}
        {#if integrationsResource.data.find((item) => item.provider_name === provider.name)?.last_error}
          <p class="mt-3 text-xs text-danger">
            {integrationsResource.data.find((item) => item.provider_name === provider.name)
              ?.last_error}
          </p>
        {/if}
        {#if integration(provider.name)?.has_credentials && status(provider.name) !== 'DISCONNECTED'}
          <p class="text-muted mt-2 text-[10px]">
            {status(provider.name) === 'CONNECTED'
              ? t('integrations.credentialsVerified')
              : status(provider.name) === 'ERROR'
                ? t('integrations.credentialVerificationFailed')
                : t('integrations.credentialsPendingVerification')}
          </p>
        {/if}
        <div class="mt-6 flex flex-wrap items-center justify-between gap-2">
          <span
            class="font-mono text-[10px] {status(provider.name) === 'CONNECTED'
              ? 'text-accent'
              : 'text-muted'}"
            >{provider.active ? status(provider.name) : t('integrations.comingSoon')}</span
          >
          <div class="flex flex-wrap gap-2">
            {#if provider.name === 'github'}
              <Button variant="primary" onclick={installGithubApp}>
                {status('github') === 'CONNECTED'
                  ? t('integrations.reconnectGithub')
                  : t('integrations.connectGithub')}
              </Button>
            {/if}
            {#if provider.name === 'github' && status('github') === 'CONNECTED'}
              <a
                class="border-line rounded-lg border px-3 py-2 text-xs text-muted hover:border-brand hover:text-brand"
                href={resolve('/repositories')}
              >
                {t('integrations.chooseRepositories')}
              </a>
            {/if}
            {#if provider.name !== 'github'}<Button
                disabled={!provider.active}
                onclick={() => {
                  editing = provider.name;
                  credential = '';
                  const existing = integrationsResource.data.find(
                    (item) => item.provider_name === provider.name
                  )?.configuration;
                  triggerLabel = String(existing?.trigger_label || 'AI Ready');
                  repositoryId = String(existing?.repository_id || '');
                  inReviewStateId = String(existing?.in_review_state_id || '');
                  readyForTestingStateId = String(existing?.ready_for_testing_state_id || '');
                  todoStateId = String(existing?.todo_state_id || '');
                  inProgressStateId = String(existing?.in_progress_state_id || '');
                  blockedStateId = String(existing?.blocked_state_id || '');
                  doneStateId = String(existing?.done_state_id || '');
                  registryUrl = String(existing?.registry_url || existing?.index_url || '');
                }}
                >{provider.name === 'github' && status(provider.name) === 'DISCONNECTED'
                  ? t('integrations.connectGithub')
                  : status(provider.name) === 'DISCONNECTED'
                    ? t('integrations.configure')
                    : t('integrations.update')}</Button
              >{/if}
          </div>
        </div>
      </article>{/each}
  </div>
</main>
