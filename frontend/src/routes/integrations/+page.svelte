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
    listLinearWorkflowStates,
    listTrelloBoards,
    listTrelloLists,
    requestIntegrationSync
  } from '$lib/services/integrations';
  import { integrationsResource, webhookHealthResource } from '$lib/stores/integrations.svelte';
  import { repositoriesResource } from '$lib/stores/repositories.svelte';
  import LinearWorkflowFields from '$lib/components/integrations/LinearWorkflowFields.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import ResourceModal from '$lib/components/resources/ResourceModal.svelte';
  import ResourceStatus from '$lib/components/resources/ResourceStatus.svelte';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';
  import type {
    GitHubInstallationAccount,
    LinearWorkflowState,
    TrelloBoard,
    TrelloList
  } from '$lib/types';
  import { t } from '$lib/i18n/index.svelte';
  const providers = [
    { name: 'github', type: 'source_control', label: 'GitHub', active: true },
    { name: 'linear', type: 'task_management', label: 'Linear', active: true },
    { name: 'trello', type: 'task_management', label: 'Trello', active: true },
    { name: 'openai', type: 'ai', label: 'OpenAI', active: true },
    { name: 'anthropic', type: 'ai', label: 'Anthropic', active: true },
    { name: 'google', type: 'ai', label: 'Google', active: true },
    { name: 'npm_registry', type: 'package_registry', label: 'npm Registry', active: true },
    { name: 'pypi_registry', type: 'package_registry', label: 'PyPI Registry', active: true },
    { name: 'gitlab', type: 'source_control', label: 'GitLab', active: false },
    { name: 'jira', type: 'task_management', label: 'Jira', active: false }
  ];
  const groups = [
    { type: 'source_control', label: 'Source control' },
    { type: 'task_management', label: 'Task management' },
    { type: 'ai', label: 'AI providers' },
    { type: 'package_registry', label: 'Package registries' }
  ];
  const credentialHelp: Record<
    string,
    { label: string; description: string; url: string; action: string }
  > = {
    linear: {
      label: 'Linear personal API key',
      description: 'Create a personal API key in Linear Settings → Security & access → API.',
      url: 'https://linear.app/settings/api',
      action: 'Open Linear API settings'
    },
    openai: {
      label: 'OpenAI API key',
      description: 'Use a secret API key created for your OpenAI Platform project.',
      url: 'https://platform.openai.com/api-keys',
      action: 'Open OpenAI API keys'
    },
    anthropic: {
      label: 'Anthropic API key',
      description: 'Use an API key created in the Anthropic Console.',
      url: 'https://console.anthropic.com/settings/keys',
      action: 'Open Anthropic API keys'
    },
    google: {
      label: 'Google Gemini API key',
      description: 'Create a Gemini API key in Google AI Studio.',
      url: 'https://aistudio.google.com/apikey',
      action: 'Open Google AI Studio'
    },
    npm_registry: {
      label: 'npm access token',
      description: 'Use a granular access token that can read the packages your workers need.',
      url: 'https://www.npmjs.com/settings/~/tokens',
      action: 'Open npm access tokens'
    },
    pypi_registry: {
      label: 'PyPI API token',
      description: 'Use a scoped PyPI API token for the required project or account.',
      url: 'https://pypi.org/manage/account/token/',
      action: 'Open PyPI API tokens'
    }
  };
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
  let trelloApiKey = '';
  let trelloToken = '';
  let trelloBoardId = '';
  let trelloListIds: string[] = [];
  let trelloBoards: TrelloBoard[] = [];
  let trelloLists: TrelloList[] = [];
  let loadingTrello = false;
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
            : provider.name === 'trello'
              ? {
                  board_id: trelloBoardId || null,
                  list_ids: trelloListIds,
                  repository_id: repositoryId || null,
                  sync_enabled: true,
                  poll_interval_seconds: 60
                }
              : provider.name === 'npm_registry'
                ? { registry_url: registryUrl || null }
                : provider.name === 'pypi_registry'
                  ? { index_url: registryUrl || null }
                  : {},
        credential:
          provider.name === 'trello'
            ? trelloApiKey && trelloToken
              ? JSON.stringify({ api_key: trelloApiKey, token: trelloToken })
              : null
            : credential || null
      });
      await testIntegration(provider.name);
      credential = '';
      trelloApiKey = '';
      trelloToken = '';
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
  async function discoverTrelloBoards() {
    loadingTrello = true;
    error = '';
    try {
      trelloBoards = await listTrelloBoards();
    } catch (cause) {
      error = String(cause);
    } finally {
      loadingTrello = false;
    }
  }
  async function continueTrelloSetup() {
    if (!trelloApiKey || !trelloToken) return;
    saving = true;
    error = '';
    try {
      await saveIntegration('trello', {
        provider_type: 'task_management',
        status: 'CONFIGURED',
        configuration: {
          board_id: trelloBoardId || null,
          list_ids: trelloListIds,
          repository_id: repositoryId || null,
          sync_enabled: true,
          poll_interval_seconds: 60
        },
        credential: JSON.stringify({ api_key: trelloApiKey, token: trelloToken })
      });
      await testIntegration('trello');
      await integrationsResource.refresh();
      trelloApiKey = '';
      trelloToken = '';
      await discoverTrelloBoards();
    } catch (cause) {
      error = String(cause);
    } finally {
      saving = false;
    }
  }
  async function discoverTrelloLists() {
    if (!trelloBoardId) return;
    loadingTrello = true;
    error = '';
    try {
      trelloLists = await listTrelloLists(trelloBoardId);
      trelloListIds = trelloListIds.filter((id) => trelloLists.some((item) => item.id === id));
    } catch (cause) {
      error = String(cause);
    } finally {
      loadingTrello = false;
    }
  }
  function toggleTrelloList(id: string, checked: boolean) {
    trelloListIds = checked
      ? Array.from(new Set([...trelloListIds, id]))
      : trelloListIds.filter((value) => value !== id);
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
  async function syncNow(providerName: string) {
    error = '';
    try {
      await requestIntegrationSync(providerName);
      await integrationsResource.refresh();
    } catch (cause) {
      error = String(cause);
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
  <div class="space-y-8">
    {#each groups as group (group.type)}
      <section>
        <h2 class="mb-3 font-mono text-xs tracking-[0.16em] text-muted uppercase">
          {group.label}
        </h2>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {#each providers.filter((provider) => provider.type === group.type) as provider (provider.name)}<article
              class="border-line bg-panel rounded-xl border p-5 transition-colors hover:border-brand"
            >
              <p class="text-muted font-mono text-[10px] tracking-widest uppercase">
                {provider.type.replaceAll('_', ' ')}
              </p>
              <div class="my-2 flex items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span
                    class="border-line bg-panel-alt grid size-10 place-items-center rounded-xl border"
                  >
                    <BrandIcon brand={provider.name} size={22} labelled />
                  </span>
                  <h3 class="text-xl font-semibold">{provider.label}</h3>
                </div>
                <ResourceStatus
                  state={provider.active
                    ? integration(provider.name)?.display_status || 'NOT_CONFIGURED'
                    : 'DISABLED'}
                  detail={integration(provider.name)?.last_error || ''}
                />
              </div>
              {#if integration(provider.name)?.usage}
                {@const usage = integration(provider.name)!.usage}
                <p class="text-muted mb-3 text-xs">
                  {usage.repositories_count || 0} repositories · {usage.teams_count || 0} teams ·
                  {usage.active_tasks_count || 0} active tasks
                </p>
              {/if}
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
                <ResourceModal
                  title={provider.label}
                  description="Connection, health, and provider configuration"
                  onClose={() => (editing = '')}
                >
                  <form
                    class="mt-4"
                    onsubmit={(event) => {
                      event.preventDefault();
                      save(provider);
                    }}
                  >
                    {#if provider.name !== 'trello'}
                      {@const help = credentialHelp[provider.name]}
                      {#if help}
                        <div class="border-line bg-panel-alt mb-4 rounded-lg border p-3 text-xs">
                          <p class="font-semibold">Required credential: {help.label}</p>
                          <p class="text-muted mt-1 leading-relaxed">{help.description}</p>
                          <button
                            type="button"
                            class="mt-2 font-medium text-brand hover:underline"
                            onclick={() => window.open(help.url, '_blank', 'noopener,noreferrer')}
                            >{help.action} →</button
                          >
                        </div>
                      {/if}
                      <TextField
                        id={`credential-${provider.name}`}
                        label={`${help?.label || 'Credential'} ${
                          integrationsResource.data.find(
                            (item) => item.provider_name === provider.name
                          )?.has_credentials
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
                    {/if}
                    {#if provider.name === 'trello'}
                      <div class="space-y-3">
                        <div class="border-brand/30 bg-brand/5 rounded-lg border p-3 text-xs">
                          <p class="font-semibold">Trello requires two credentials</p>
                          <p class="text-muted mt-1 leading-relaxed">
                            Use the API key generated for a Trello app, then generate its Trello
                            user token. An Atlassian account API token is different and will not
                            work here.
                          </p>
                          <a
                            class="mt-2 inline-block font-medium text-brand hover:underline"
                            href="https://trello.com/apps/admin"
                            target="_blank"
                            rel="noreferrer">Open Trello App Admin →</a
                          >
                        </div>
                        <TextField
                          id="trello-api-key"
                          label={`${t('integrations.trelloApiKey')} ${integration('trello')?.has_credentials ? t('integrations.keepExisting') : ''}`}
                          type="password"
                          bind:value={trelloApiKey}
                          autocomplete="off"
                          required={!integration('trello')?.has_credentials}
                        />
                        <TextField
                          id="trello-token"
                          label={t('integrations.trelloToken')}
                          type="password"
                          bind:value={trelloToken}
                          autocomplete="off"
                          required={!integration('trello')?.has_credentials}
                        />
                        <Button
                          type="button"
                          size="sm"
                          onclick={discoverTrelloBoards}
                          disabled={loadingTrello || !integration('trello')?.has_credentials}
                        >
                          {loadingTrello
                            ? t('common.loading')
                            : t('integrations.trelloDiscoverBoards')}
                        </Button>
                        {#if !integration('trello')?.has_credentials}
                          <Button
                            type="button"
                            variant="primary"
                            onclick={continueTrelloSetup}
                            disabled={saving || !trelloApiKey || !trelloToken}
                            >Continue to boards</Button
                          >
                        {/if}
                        <label class="text-muted block text-xs" for="trello-board"
                          >{t('integrations.trelloBoard')}</label
                        >
                        <select
                          id="trello-board"
                          class="border-line bg-panel-alt w-full rounded-lg border p-2 text-sm"
                          bind:value={trelloBoardId}
                          onchange={discoverTrelloLists}
                        >
                          <option value="">{t('integrations.trelloSelectBoard')}</option>
                          {#each trelloBoards as board (board.id)}<option value={board.id}
                              >{board.name}</option
                            >{/each}
                        </select>
                        {#if trelloLists.length}
                          <fieldset class="space-y-2">
                            <legend class="text-muted text-xs">
                              {t('integrations.trelloSourceLists')}
                            </legend>
                            {#each trelloLists as list (list.id)}
                              <label class="flex items-center gap-2 text-sm">
                                <input
                                  type="checkbox"
                                  checked={trelloListIds.includes(list.id)}
                                  onchange={(event) =>
                                    toggleTrelloList(list.id, event.currentTarget.checked)}
                                />
                                {list.name}
                              </label>
                            {/each}
                          </fieldset>
                        {/if}
                        <label class="text-muted block text-xs" for="trello-repository"
                          >{t('integrations.repositoryForNewTasks')}</label
                        >
                        <select
                          id="trello-repository"
                          class="border-line bg-panel-alt w-full rounded-lg border p-2 text-sm"
                          bind:value={repositoryId}
                        >
                          <option value="">{t('integrations.noAutomaticRepository')}</option>
                          {#each repositoriesResource.data as repository (repository.id)}<option
                              value={repository.id}>{repository.owner}/{repository.name}</option
                            >{/each}
                        </select>
                        {#if !integration('trello')?.has_credentials}<p
                            class="text-muted text-[10px]"
                          >
                            {t('integrations.trelloSaveThenDiscover')}
                          </p>{/if}
                      </div>
                    {/if}
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
                        >{saving
                          ? t('integrations.saving')
                          : t('integrations.saveSecurely')}</Button
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
                </ResourceModal>
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
              {#if ['linear', 'trello'].includes(provider.name) && integration(provider.name)}
                <div class="border-line bg-panel-alt mt-3 rounded-lg border p-3 text-xs">
                  <span class="text-muted">Sync</span>
                  <strong class="ml-2">{integration(provider.name)?.sync_status}</strong>
                  <p class="text-muted mt-1 text-[10px]">
                    Last sync:
                    {integration(provider.name)?.last_synced_at
                      ? new Date(integration(provider.name)!.last_synced_at!).toLocaleString()
                      : 'Never'}
                  </p>
                </div>
              {/if}
              <div class="mt-6 flex flex-wrap items-center justify-between gap-2">
                {#if integrationsResource.loading && integrationsResource.data.length === 0}
                  <Skeleton class="h-3 w-20" />
                {:else}
                  <span
                    class="font-mono text-[10px] {status(provider.name) === 'CONNECTED'
                      ? 'text-accent'
                      : 'text-muted'}"
                    >{provider.active ? status(provider.name) : t('integrations.comingSoon')}</span
                  >
                {/if}
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
                  {#if ['linear', 'trello'].includes(provider.name) && status(provider.name) === 'CONNECTED'}
                    <Button size="sm" onclick={() => syncNow(provider.name)}>Sync now</Button>
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
                        trelloBoardId = String(existing?.board_id || '');
                        trelloListIds = Array.isArray(existing?.list_ids)
                          ? existing.list_ids.map(String)
                          : [];
                        trelloApiKey = '';
                        trelloToken = '';
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
      </section>
    {/each}
  </div>
</main>
