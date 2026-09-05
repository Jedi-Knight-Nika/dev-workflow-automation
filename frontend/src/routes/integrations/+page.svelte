<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/PageHeader.svelte';
  import { api } from '$lib/api';
  import type { Integration, LinearWorkflowState, Repository, WebhookHealth } from '$lib/types';
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
  let integrations: Integration[] = [];
  let webhookHealth: WebhookHealth[] = [];
  let repositories: Repository[] = [];
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
      const result = await api<{ url: string }>('/github/app/install-url');
      window.location.assign(result.url);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function load() {
    [integrations, repositories, webhookHealth] = await Promise.all([
      api<Integration[]>('/integrations'),
      api<Repository[]>('/repositories'),
      api<WebhookHealth[]>('/webhook-health')
    ]);
  }
  onMount(async () => {
    try {
      await load();
    } catch (cause) {
      error = String(cause);
    }
  });
  function status(name: string) {
    return integrations.find((item) => item.provider_name === name)?.status || 'DISCONNECTED';
  }
  function deliveryHealth(name: string) {
    return webhookHealth.find((item) => item.provider === name);
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
      await api(`/integrations/${provider.name}`, {
        method: 'PUT',
        body: JSON.stringify({
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
        })
      });
      credential = '';
      editing = '';
      await load();
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
      linearStates = await api<LinearWorkflowState[]>('/linear/workflow-states');
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
      await api(`/integrations/${providerName}/test`, { method: 'POST' });
      await load();
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
<main class="p-6 md:p-10">
  {#if error}<p class="mb-4 bg-red-950 p-3 text-red-300">{error}</p>{/if}
  <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
    {#each providers as provider (provider.name)}<article class="border-line bg-panel border p-5">
        <p class="text-muted font-mono text-[10px] tracking-widest uppercase">
          {provider.type.replaceAll('_', ' ')}
        </p>
        <h2 class="my-2 text-xl font-semibold">{provider.label}</h2>
        {#if deliveryHealth(provider.name)}
          {@const health = deliveryHealth(provider.name)!}
          <div class="border-line mb-3 grid grid-cols-2 border font-mono text-[10px]">
            <span class="border-line border-r p-2">WEBHOOK PENDING {health.pending}</span>
            <span class="p-2 {health.failed ? 'text-red-300' : 'text-accent'}"
              >FAILED {health.failed}</span
            >
          </div>
          {#if health.last_error}
            <p class="mb-3 text-xs text-red-300">Last delivery error: {health.last_error}</p>
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
              <label class="text-muted mb-3 block text-xs"
                >Authentication<select
                  class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                  bind:value={githubAuthType}
                  ><option value="token">Personal access token</option><option value="github_app"
                    >GitHub App installation</option
                  ></select
                ></label
              >
            {/if}
            {#if provider.name !== 'github' || githubAuthType === 'token'}
              <label class="text-muted text-xs" for={`credential-${provider.name}`}
                >API key or token {integrations.find((item) => item.provider_name === provider.name)
                  ?.has_credentials
                  ? '(leave blank to keep existing)'
                  : ''}</label
              >
              <input
                id={`credential-${provider.name}`}
                class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm outline-none focus:border-accent"
                type="password"
                bind:value={credential}
                autocomplete="off"
                required={!integrations.find((item) => item.provider_name === provider.name)
                  ?.has_credentials}
              />
            {:else}
              <input
                class="border-line mb-2 mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                bind:value={githubAppSlug}
                placeholder="GitHub App slug (from its public URL)"
                pattern="[A-Za-z0-9-]+"
                title="Letters, numbers, and hyphens only"
                required
              />
              <input
                class="border-line mb-2 w-full border bg-[#090c0a] p-2.5 text-sm"
                bind:value={githubAppId}
                placeholder="GitHub App ID"
                inputmode="numeric"
                pattern="[0-9]+"
                required={!integrations.find((item) => item.provider_name === 'github')
                  ?.has_credentials}
              />
              <input
                class="border-line mb-2 w-full border bg-[#090c0a] p-2.5 text-sm"
                bind:value={githubInstallationId}
                placeholder="Installation ID (filled after installation)"
              />
              <textarea
                class="border-line h-32 w-full border bg-[#090c0a] p-2.5 font-mono text-xs"
                bind:value={githubPrivateKey}
                placeholder="-----BEGIN RSA PRIVATE KEY-----"
                required={!integrations.find((item) => item.provider_name === 'github')
                  ?.has_credentials}
              ></textarea>
            {/if}
            {#if provider.name === 'linear'}
              <label class="text-muted mt-3 block text-xs" for="linear-trigger-label"
                >Trigger label</label
              >
              <input
                id="linear-trigger-label"
                class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm outline-none focus:border-accent"
                bind:value={triggerLabel}
                required
              />
              <label class="text-muted mt-3 block text-xs" for="linear-repository"
                >Repository for new tasks</label
              >
              <select
                id="linear-repository"
                class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                bind:value={repositoryId}
              >
                <option value="">No automatic repository</option>
                {#each repositories as repository (repository.id)}<option value={repository.id}
                    >{repository.owner}/{repository.name}</option
                  >{/each}
              </select>
              <div class="mt-3 flex items-end justify-between gap-3">
                <label class="text-muted block text-xs" for="linear-ready-state"
                  >Ready for Testing workflow state</label
                >
                <button
                  class="border-line border px-2 py-1 text-[10px] disabled:opacity-40"
                  type="button"
                  disabled={loadingLinearStates ||
                    !integrations.find((item) => item.provider_name === 'linear')?.has_credentials}
                  onclick={discoverLinearStates}
                  >{loadingLinearStates ? 'Loading…' : 'Discover states'}</button
                >
              </div>
              <label class="text-muted mt-3 block text-xs" for="linear-in-review-state"
                >In Review workflow state</label
              >
              <div class="mt-3 grid gap-3 sm:grid-cols-2">
                <label class="text-muted text-xs" for="linear-todo-state"
                  >Todo state
                  <select
                    id="linear-todo-state"
                    class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                    bind:value={todoStateId}
                  >
                    <option value="">Do not synchronize</option>
                    {#each linearStates as state (state.id)}<option value={state.id}
                        >{state.team_key || state.team_name} — {state.name}</option
                      >{/each}
                  </select></label
                >
                <label class="text-muted text-xs" for="linear-progress-state"
                  >In Progress state
                  <select
                    id="linear-progress-state"
                    class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                    bind:value={inProgressStateId}
                  >
                    <option value="">Do not synchronize</option>
                    {#each linearStates as state (state.id)}<option value={state.id}
                        >{state.team_key || state.team_name} — {state.name}</option
                      >{/each}
                  </select></label
                >
                <label class="text-muted text-xs" for="linear-blocked-state"
                  >Blocked state
                  <select
                    id="linear-blocked-state"
                    class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                    bind:value={blockedStateId}
                  >
                    <option value="">Do not synchronize</option>
                    {#each linearStates as state (state.id)}<option value={state.id}
                        >{state.team_key || state.team_name} — {state.name}</option
                      >{/each}
                  </select></label
                >
                <label class="text-muted text-xs" for="linear-done-state"
                  >Done state
                  <select
                    id="linear-done-state"
                    class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                    bind:value={doneStateId}
                  >
                    <option value="">Do not synchronize</option>
                    {#each linearStates as state (state.id)}<option value={state.id}
                        >{state.team_key || state.team_name} — {state.name}</option
                      >{/each}
                  </select></label
                >
              </div>
              {#if linearStates.length > 0}
                <select
                  id="linear-in-review-state"
                  class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                  bind:value={inReviewStateId}
                >
                  <option value="">Do not update after PR publication</option>
                  {#each linearStates as state (state.id)}
                    <option value={state.id}
                      >{state.team_key || state.team_name} — {state.name}</option
                    >
                  {/each}
                </select>
              {:else}
                <input
                  id="linear-in-review-state"
                  class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm outline-none focus:border-accent"
                  bind:value={inReviewStateId}
                  placeholder="Save credentials, then discover states"
                />
              {/if}
              {#if linearStates.length > 0}
                <select
                  id="linear-ready-state"
                  class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm"
                  bind:value={readyForTestingStateId}
                >
                  <option value="">Do not update after merge</option>
                  {#each linearStates as state (state.id)}
                    <option value={state.id}
                      >{state.team_key || state.team_name} — {state.name}</option
                    >
                  {/each}
                </select>
              {:else}
                <input
                  id="linear-ready-state"
                  class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm outline-none focus:border-accent"
                  bind:value={readyForTestingStateId}
                  placeholder="Save credentials, then discover states"
                />
              {/if}
            {/if}
            {#if provider.name === 'npm_registry' || provider.name === 'pypi_registry'}
              <label class="text-muted mt-3 block text-xs" for={`registry-url-${provider.name}`}
                >{provider.name === 'npm_registry' ? 'Registry URL' : 'Package index URL'}</label
              >
              <input
                id={`registry-url-${provider.name}`}
                class="border-line mt-1 w-full border bg-[#090c0a] p-2.5 text-sm outline-none focus:border-accent"
                type="url"
                bind:value={registryUrl}
                placeholder={provider.name === 'npm_registry'
                  ? 'https://npm.pkg.github.com'
                  : 'https://pypi.example.com/simple'}
              />
            {/if}
            <p class="text-muted mt-2 text-[10px]">
              Stored encrypted. The value is never returned to the browser.
            </p>
            <div class="mt-3 flex gap-2">
              <button
                class="bg-accent px-3 py-1.5 text-xs font-bold text-[#07100a]"
                type="submit"
                disabled={saving}>{saving ? 'Saving…' : 'Save securely'}</button
              ><button
                class="border-line border px-3 py-1.5 text-xs"
                type="button"
                onclick={() => {
                  editing = '';
                  credential = '';
                }}>Cancel</button
              >
            </div>
          </form>
        {/if}
        {#if integrations.find((item) => item.provider_name === provider.name)?.last_error}
          <p class="mt-3 text-xs text-red-300">
            {integrations.find((item) => item.provider_name === provider.name)?.last_error}
          </p>
        {/if}
        <div class="mt-6 flex items-center justify-between gap-2">
          <span
            class="font-mono text-[10px] {status(provider.name) === 'CONNECTED'
              ? 'text-accent'
              : 'text-[#7f8982]'}">{provider.active ? status(provider.name) : 'COMING SOON'}</span
          >
          <div class="flex gap-2">
            {#if provider.name === 'github' && integrations.find((item) => item.provider_name === 'github')?.has_credentials && integrations.find((item) => item.provider_name === 'github')?.configuration?.auth_type === 'github_app'}
              <button class="border-line border px-3 py-1.5 text-xs" onclick={installGithubApp}
                >Install app</button
              >
            {/if}
            {#if provider.active && integrations.find((item) => item.provider_name === provider.name)?.has_credentials}
              <button
                class="border-line border px-3 py-1.5 text-xs disabled:opacity-40"
                disabled={testing === provider.name}
                onclick={() => testConnection(provider.name)}
                >{testing === provider.name ? 'Testing…' : 'Test'}</button
              >
            {/if}
            <button
              disabled={!provider.active}
              onclick={() => {
                editing = provider.name;
                credential = '';
                const existing = integrations.find(
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
              }}
              class="border-line border px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-30"
              >{status(provider.name) === 'DISCONNECTED' ? 'Configure' : 'Update'}</button
            >
          </div>
        </div>
      </article>{/each}
  </div>
</main>
