<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import {
    saveIntegration,
    testIntegration,
    getGithubAppInstallUrl,
    listLinearWorkflowStates
  } from '$lib/services/integrations';
  import { integrationsResource, webhookHealthResource } from '$lib/stores/integrations.svelte';
  import { repositoriesResource } from '$lib/stores/repositories.svelte';
  import GithubAppFields from '$lib/components/integrations/GithubAppFields.svelte';
  import LinearWorkflowFields from '$lib/components/integrations/LinearWorkflowFields.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import Select from '$lib/components/Select.svelte';
  import type { LinearWorkflowState } from '$lib/types';
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
  let testing = '';
  let githubAuthType = 'token';
  let githubAppSlug = '';
  let githubAppId = '';
  let githubInstallationId = '';
  let githubPrivateKey = '';
  let registryUrl = '';
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
  });
  function status(name: string) {
    return (
      integrationsResource.data.find((item) => item.provider_name === name)?.status ||
      'DISCONNECTED'
    );
  }
  function deliveryHealth(name: string) {
    return webhookHealthResource.data.find((item) => item.provider === name);
  }
  async function save(provider: (typeof providers)[number]) {
    saving = true;
    error = '';
    try {
      const githubAppCredential =
        provider.name === 'github' && githubAuthType === 'github_app' && githubPrivateKey
          ? JSON.stringify({
              auth_type: 'github_app',
              app_id: githubAppId,
              installation_id: githubInstallationId,
              private_key: githubPrivateKey
            })
          : null;
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
            : provider.name === 'github'
              ? { auth_type: githubAuthType, app_slug: githubAppSlug || null }
              : provider.name === 'npm_registry'
                ? { registry_url: registryUrl || null }
                : provider.name === 'pypi_registry'
                  ? { index_url: registryUrl || null }
                  : {},
        credential: githubAppCredential || credential || null
      });
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
  async function testConnection(providerName: string) {
    testing = providerName;
    error = '';
    try {
      await testIntegration(providerName);
      await integrationsResource.refresh();
    } catch (cause) {
      error = String(cause);
    } finally {
      testing = '';
    }
  }
</script>

<PageHeader
  eyebrow="CONNECTIONS"
  title="Integrations"
  description="External systems and AI providers available to the orchestrator."
/>
<main class="p-4 sm:p-6 md:p-10">
  <ErrorBanner
    message={error || integrationsResource.error || webhookHealthResource.error}
    class="mb-4"
  />
  <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
    {#each providers as provider, index (provider.name)}<article
        class="border-line bg-panel rounded-xl border p-5 card-hover motion-safe:animate-fade-in-up"
        style="animation-delay: {index * 40}ms"
      >
        <p class="text-muted font-mono text-[10px] tracking-widest uppercase">
          {provider.type.replaceAll('_', ' ')}
        </p>
        <h2 class="my-2 text-xl font-semibold">{provider.label}</h2>
        {#if deliveryHealth(provider.name)}
          {@const health = deliveryHealth(provider.name)!}
          <div
            class="border-line mb-3 grid grid-cols-2 overflow-hidden rounded-lg border font-mono text-[10px]"
          >
            <span class="border-line border-r p-2">WEBHOOK PENDING {health.pending}</span>
            <span class="p-2 {health.failed ? 'text-danger' : 'text-accent'}"
              >FAILED {health.failed}</span
            >
          </div>
          {#if health.last_error}
            <p class="mb-3 text-xs text-danger">Last delivery error: {health.last_error}</p>
          {/if}
        {/if}
        {#if editing === provider.name}
          <form
            class="mt-4"
            onsubmit={(event) => {
              event.preventDefault();
              save(provider);
            }}
          >
            {#if provider.name === 'github'}
              <label class="text-muted mb-1.5 block text-xs" for={`auth-type-${provider.name}`}
                >Authentication</label
              >
              <Select id={`auth-type-${provider.name}`} bind:value={githubAuthType} class="mb-3">
                <option value="token">Personal access token</option>
                <option value="github_app">GitHub App installation</option>
              </Select>
            {/if}
            {#if provider.name !== 'github' || githubAuthType === 'token'}
              <TextField
                id={`credential-${provider.name}`}
                label={`API key or token ${
                  integrationsResource.data.find((item) => item.provider_name === provider.name)
                    ?.has_credentials
                    ? '(leave blank to keep existing)'
                    : ''
                }`}
                type="password"
                bind:value={credential}
                autocomplete="off"
                required={!integrationsResource.data.find(
                  (item) => item.provider_name === provider.name
                )?.has_credentials}
              />
            {:else}
              <GithubAppFields
                bind:appSlug={githubAppSlug}
                bind:appId={githubAppId}
                bind:installationId={githubInstallationId}
                bind:privateKey={githubPrivateKey}
                hasCredentials={!!integrationsResource.data.find(
                  (item) => item.provider_name === 'github'
                )?.has_credentials}
              />
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
                label={provider.name === 'npm_registry' ? 'Registry URL' : 'Package index URL'}
                type="url"
                bind:value={registryUrl}
                placeholder={provider.name === 'npm_registry'
                  ? 'https://npm.pkg.github.com'
                  : 'https://pypi.example.com/simple'}
                class="mt-3"
              />
            {/if}
            <p class="text-muted mt-2 text-[10px]">
              Stored encrypted. The value is never returned to the browser.
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Button variant="primary" type="submit" disabled={saving}
                >{saving ? 'Saving…' : 'Save securely'}</Button
              >
              <Button
                type="button"
                onclick={() => {
                  editing = '';
                  credential = '';
                }}>Cancel</Button
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
        <div class="mt-6 flex flex-wrap items-center justify-between gap-2">
          <span
            class="font-mono text-[10px] {status(provider.name) === 'CONNECTED'
              ? 'text-accent'
              : 'text-muted'}">{provider.active ? status(provider.name) : 'COMING SOON'}</span
          >
          <div class="flex flex-wrap gap-2">
            {#if provider.name === 'github' && integrationsResource.data.find((item) => item.provider_name === 'github')?.has_credentials && integrationsResource.data.find((item) => item.provider_name === 'github')?.configuration?.auth_type === 'github_app'}
              <Button onclick={installGithubApp}>Install app</Button>
            {/if}
            {#if provider.active && integrationsResource.data.find((item) => item.provider_name === provider.name)?.has_credentials}
              <Button
                disabled={testing === provider.name}
                onclick={() => testConnection(provider.name)}
                >{testing === provider.name ? 'Testing…' : 'Test'}</Button
              >
            {/if}
            <Button
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
                githubAuthType = String(existing?.auth_type || 'token');
                githubAppSlug = String(existing?.app_slug || '');
                githubAppId = '';
                githubInstallationId = '';
                githubPrivateKey = '';
                registryUrl = String(existing?.registry_url || existing?.index_url || '');
              }}>{status(provider.name) === 'DISCONNECTED' ? 'Configure' : 'Update'}</Button
            >
          </div>
        </div>
      </article>{/each}
  </div>
</main>
