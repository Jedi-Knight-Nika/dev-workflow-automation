<script lang="ts">
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { API_URL } from '$lib/api';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TextArea from '$lib/components/TextArea.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import TerminalConsole from '$lib/components/workflow/TerminalConsole.svelte';
  import AgentRuntimePanel from '$lib/components/workflow/AgentRuntimePanel.svelte';
  import ResourceModal from '$lib/components/resources/ResourceModal.svelte';
  import type { default as WorkflowCanvasComponent } from '$lib/components/workflow/WorkflowCanvas.svelte';
  import {
    addAgentKnowledge,
    deleteAgentKnowledge,
    discoverProviderModels,
    getAgentRuntime,
    getModelCapabilities,
    getWorkflow,
    listAgentKnowledge,
    listAgents,
    saveAgent,
    saveWorkflow,
    resetAgentRuntime,
    updateAgentRuntime
  } from '$lib/services/agents';
  import { listIntegrations } from '$lib/services/integrations';
  import { listRepositories } from '$lib/services/repositories';
  import { listTeams } from '$lib/services/teams';
  import { t } from '$lib/i18n/index.svelte';
  import { providerModelOptions } from '$lib/ai-model-catalog';
  import PixelAgentAvatar from '$lib/components/agents/PixelAgentAvatar.svelte';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';
  import type {
    AgentConfig,
    AgentKnowledge,
    AgentRuntimeView,
    Integration,
    ModelCapabilities,
    ProviderCatalog,
    Repository,
    Team,
    WorkflowGraph
  } from '$lib/types';
  let agents: AgentConfig[] = [];
  let error = '';
  let saved = '';
  let catalogs: Record<string, ProviderCatalog> = {};
  let loadingProvider = '';
  let selectedRole = 'INTAKE';
  let knowledge: Record<string, AgentKnowledge[]> = {};
  let knowledgeTitle = '';
  let knowledgeContent = '';
  let preparingKnowledge = false;
  let workflow: WorkflowGraph | null = null;
  let integrations: Integration[] = [];
  let repositories: Repository[] = [];
  let selectedNodeId = '';
  let consoleAgent: AgentConfig | null = null;
  let inspectorTab = 'instructions';
  let agentRuntime: AgentRuntimeView | null = null;
  let modelCapabilities: ModelCapabilities | null = null;
  let runtimeLoading = false;
  let WorkflowCanvas: typeof WorkflowCanvasComponent | null = null;
  let teams: Team[] = [];
  let currentTeamId = page.url.searchParams.get('team') || '';
  let teamId: string | undefined = currentTeamId || undefined;
  let workflowDirty = false;
  let pendingTeamId: string | null = null;
  const manualModelRoles = new SvelteSet<string>();
  const number = new Intl.NumberFormat();
  const date = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  function configuredNumber(agent: AgentConfig, key: string): number | '' {
    const value = Number(agent.configuration[key]);
    return Number.isFinite(value) ? value : '';
  }
  function setConfiguredNumber(agent: AgentConfig, key: string, event: Event) {
    const value = (event.currentTarget as HTMLInputElement).value;
    agent.configuration[key] = value === '' ? null : Number(value);
  }
  function configuredText(agent: AgentConfig, key: string) {
    return typeof agent.configuration[key] === 'string' ? String(agent.configuration[key]) : '';
  }
  function setConfiguredText(agent: AgentConfig, key: string, value: string) {
    agent.configuration[key] = value;
  }
  function availableModels(agent: AgentConfig) {
    return providerModelOptions(agent.provider, catalogs[agent.provider]?.models || []);
  }
  function usesManualModel(agent: AgentConfig) {
    return (
      manualModelRoles.has(agent.role) ||
      (!!agent.model && !availableModels(agent).some((model) => model.id === agent.model))
    );
  }
  function changeProvider(agent: AgentConfig, event: Event) {
    agent.provider = (event.currentTarget as HTMLSelectElement).value;
    agent.model = '';
    manualModelRoles.delete(agent.role);
  }
  function changeModel(agent: AgentConfig, event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (value === '__manual__') {
      agent.model = '';
      manualModelRoles.add(agent.role);
    } else {
      agent.model = value;
      manualModelRoles.delete(agent.role);
    }
  }
  function repositoryKnowledgeEnabled(agent: AgentConfig) {
    return agent.configuration.use_repository_knowledge !== false;
  }
  function setRepositoryKnowledge(agent: AgentConfig, event: Event) {
    agent.configuration.use_repository_knowledge = (
      event.currentTarget as HTMLInputElement
    ).checked;
  }
  async function load() {
    const [loadedWorkflow] = await Promise.all([
      getWorkflow(teamId),
      import('$lib/components/workflow/WorkflowCanvas.svelte').then((mod) => {
        WorkflowCanvas = mod.default;
      })
    ]);
    workflow = loadedWorkflow;
    [agents, integrations, repositories, teams] = await Promise.all([
      listAgents(),
      listIntegrations(),
      listRepositories(),
      listTeams()
    ]);
    const entries = await Promise.all(
      agents.map(async (agent) => [agent.role, await listAgentKnowledge(agent.role)] as const)
    );
    knowledge = Object.fromEntries(entries);
  }
  async function persistWorkflow(graph: WorkflowGraph) {
    try {
      workflow = await saveWorkflow(graph, teamId);
      saved = 'WORKFLOW';
      setTimeout(() => (saved = ''), 1500);
    } catch (cause) {
      error = String(cause);
      throw cause;
    }
  }

  async function switchTeam(nextTeamId: string) {
    currentTeamId = nextTeamId;
    teamId = nextTeamId || undefined;
    pendingTeamId = null;
    workflowDirty = false;
    workflow = null;
    selectedNodeId = '';
    agentRuntime = null;
    modelCapabilities = null;
    window.history.replaceState(
      window.history.state,
      '',
      nextTeamId
        ? `${resolve('/agents')}?team=${encodeURIComponent(nextTeamId)}`
        : resolve('/agents')
    );
    workflow = await getWorkflow(nextTeamId || undefined);
  }

  function requestTeamSwitch(event: Event) {
    const nextTeamId = (event.currentTarget as HTMLSelectElement).value;
    if (nextTeamId === currentTeamId) return;
    if (workflowDirty) {
      pendingTeamId = nextTeamId;
      return;
    }
    void switchTeam(nextTeamId).catch((cause) => {
      error = String(cause);
    });
  }
  async function selectAgent(role: string, nodeId: string) {
    selectedRole = role;
    selectedNodeId = nodeId;
    agentRuntime = null;
    modelCapabilities = null;
    const agentId = workflow?.nodes.find((node) => node.id === nodeId)?.agent_id;
    if (!agentId) return;
    runtimeLoading = true;
    try {
      agentRuntime = await getAgentRuntime(agentId);
      modelCapabilities = await getModelCapabilities(
        agentRuntime.effective.provider,
        agentRuntime.effective.model
      );
    } catch (cause) {
      error = String(cause);
    } finally {
      runtimeLoading = false;
    }
  }
  async function saveRuntime(overrides: Record<string, unknown>) {
    if (!agentRuntime) return;
    error = '';
    try {
      agentRuntime = await updateAgentRuntime(agentRuntime.agent_id, overrides);
      saved = 'RUNTIME';
      setTimeout(() => (saved = ''), 1500);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function resetRuntime() {
    if (!agentRuntime) return;
    error = '';
    try {
      agentRuntime = await resetAgentRuntime(agentRuntime.agent_id);
      saved = 'RUNTIME';
      setTimeout(() => (saved = ''), 1500);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function prepareKnowledge() {
    if (!knowledgeTitle.trim() || !knowledgeContent.trim()) return;
    preparingKnowledge = true;
    error = '';
    try {
      const source = await addAgentKnowledge(selectedRole, {
        title: knowledgeTitle,
        content: knowledgeContent
      });
      knowledge[selectedRole] = [source, ...(knowledge[selectedRole] || [])];
      knowledge = { ...knowledge };
      knowledgeTitle = '';
      knowledgeContent = '';
    } catch (cause) {
      error = String(cause);
    } finally {
      preparingKnowledge = false;
    }
  }
  async function removeKnowledge(source: AgentKnowledge) {
    await deleteAgentKnowledge(selectedRole, source.id);
    knowledge[selectedRole] = (knowledge[selectedRole] || []).filter(
      (item) => item.id !== source.id
    );
    knowledge = { ...knowledge };
  }
  async function save(agent: AgentConfig) {
    try {
      await saveAgent(agent.role, {
        enabled: agent.enabled,
        provider: agent.provider,
        model: agent.model,
        configuration: agent.configuration
      });
      saved = agent.role;
      setTimeout(() => {
        saved = '';
      }, 1500);
    } catch (cause) {
      error = String(cause);
    }
  }
  async function discoverModels(provider: string) {
    loadingProvider = provider;
    error = '';
    try {
      catalogs[provider] = await discoverProviderModels(provider);
      catalogs = { ...catalogs };
    } catch (cause) {
      error = String(cause);
    } finally {
      loadingProvider = '';
    }
  }
  onMount(() => {
    load().catch((cause) => {
      error = String(cause);
    });
    const events = new EventSource(`${API_URL}/api/v1/events/stream`);
    events.addEventListener('update', () => {
      listAgents()
        .then((items) => (agents = items))
        .catch(() => undefined);
    });
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!workflowDirty) return;
      event.preventDefault();
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => {
      events.close();
      window.removeEventListener('beforeunload', warnBeforeUnload);
    };
  });
</script>

<PageHeader
  eyebrow={t('workflow.eyebrow')}
  title={teamId ? 'Team workflow' : t('workflow.title')}
  description={t('workflow.description')}
/>
<main class="p-4 sm:p-6 md:p-10">
  <ErrorBanner message={error} class="mb-4" />
  <div class="border-line bg-panel mb-4 flex flex-wrap items-center gap-3 rounded-xl border p-4">
    <div class="min-w-0 flex-1">
      <label class="block text-sm font-semibold" for="workflow-team">Team workflow</label>
      <p class="text-muted mt-1 text-xs">Choose which Team's routing graph you want to edit.</p>
    </div>
    <select
      id="workflow-team"
      class="border-line bg-panel-alt min-w-56 rounded-lg border px-3 py-2 text-sm"
      value={currentTeamId}
      onchange={requestTeamSwitch}
    >
      <option value="">Default workflow</option>
      {#each teams as team (team.id)}
        <option value={team.id}>{team.name}</option>
      {/each}
    </select>
    {#if workflowDirty}
      <span class="rounded-full bg-warning/10 px-3 py-1 text-xs font-medium text-warning">
        Unsaved changes
      </span>
    {/if}
  </div>
  {#if workflow && WorkflowCanvas}
    {#key currentTeamId}
      <svelte:component
        this={WorkflowCanvas}
        {workflow}
        {agents}
        {integrations}
        {repositories}
        {selectedRole}
        {teamId}
        onSelect={(role, nodeId) => {
          void selectAgent(role, nodeId);
        }}
        onConsole={(role, nodeId) => {
          selectedNodeId = nodeId;
          consoleAgent = agents.find((agent) => agent.role === role) || null;
        }}
        onSave={persistWorkflow}
        onDirtyChange={(dirty) => (workflowDirty = dirty)}
      />
    {/key}
  {:else if !error}
    <section class="border-line bg-panel mb-6 overflow-hidden rounded-xl border" aria-busy="true">
      <div class="border-line flex min-h-16 items-center gap-3 border-b px-4 py-3">
        <Skeleton class="h-8 w-28" />
        <Skeleton class="h-4 w-40" />
        <Skeleton class="ml-auto h-8 w-24" />
      </div>
      <div class="relative flex h-[600px] items-center justify-center bg-surface">
        <div class="flex items-center gap-3">
          <Skeleton class="h-16 w-52 rounded-xl" />
          <Skeleton class="h-16 w-52 rounded-xl" />
        </div>
      </div>
    </section>
  {/if}
  <section id="agent-inspector" class="border-line bg-panel overflow-hidden rounded-xl border">
    {#if !workflow && !error}
      <div
        class="flex flex-wrap items-center gap-4 border-b border-line px-5 py-4 sm:px-6"
        aria-busy="true"
      >
        <Skeleton class="h-9 w-9 rounded-lg" />
        <Skeleton class="h-5 w-32" />
      </div>
      <div class="grid gap-3 p-5 sm:p-6" aria-busy="true">
        <Skeleton class="h-4 w-40" />
        <Skeleton class="h-24 w-full" />
      </div>
    {/if}
    {#each agents.filter((item) => item.role === selectedRole) as agent (agent.role)}
      <header class="border-line flex flex-wrap items-center gap-4 border-b px-5 py-4 sm:px-6">
        <PixelAgentAvatar
          seed={`${teamId || 'default'}:${agent.role}`}
          label={agent.role}
          size={40}
        />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="text-lg font-semibold capitalize">{agent.role.toLowerCase()}</h2>
            <span
              class="status-badge"
              class:online={agent.status === 'RUNNING' || agent.status === 'READY'}
            >
              <i></i>{agent.status.replaceAll('_', ' ')}
            </span>
          </div>
          <p class="text-muted text-xs">{t('workflow.agentContext')}</p>
        </div>
        <div class="ml-auto flex items-center gap-3">
          <Button size="sm" variant="ghost" onclick={() => (consoleAgent = agent)}
            >{t('workflow.liveConsole')}</Button
          >
          <label class="enable-control">
            <span>{agent.enabled ? t('workflow.enabled') : t('workflow.disabled')}</span>
            <input
              type="checkbox"
              bind:checked={agent.enabled}
              aria-label={`Enable ${agent.role}`}
            />
          </label>
          <Button size="sm" variant="primary" onclick={() => save(agent)}>
            {saved === agent.role ? t('workflow.savedCheck') : t('workflow.saveChanges')}
          </Button>
        </div>
      </header>

      <div class="metrics-strip">
        <div><span>{t('workflow.metricActive')}</span><b>{agent.active_jobs}</b></div>
        <div>
          <span>{t('workflow.metricTotalRuns')}</span><b>{number.format(agent.total_runs)}</b>
        </div>
        <div>
          <span>{t('workflow.metricInputTokens')}</span><b
            >{number.format(agent.total_input_tokens)}</b
          >
        </div>
        <div>
          <span>{t('workflow.metricOutputTokens')}</span><b
            >{number.format(agent.total_output_tokens)}</b
          >
        </div>
        <div>
          <span>{t('workflow.metricEstCost')}</span><b
            >${agent.total_estimated_cost_usd.toFixed(4)}</b
          >
        </div>
      </div>

      <nav class="inspector-tabs" aria-label="Agent settings">
        {#each [['instructions', t('workflow.tabInstructions')], ['model', t('workflow.tabModel')], ['runtime', 'Runtime'], ['knowledge', t('workflow.tabKnowledge')]] as tab (tab[0])}
          <button
            class:active={inspectorTab === tab[0]}
            type="button"
            onclick={() => (inspectorTab = tab[0])}>{tab[1]}</button
          >
        {/each}
      </nav>

      <div class="p-5 sm:p-6">
        {#if inspectorTab === 'instructions'}
          <div class="mx-auto max-w-4xl">
            <div class="section-heading">
              <div>
                <h3>{t('workflow.systemInstructions')}</h3>
                <p>{t('workflow.systemInstructionsDescription')}</p>
              </div>
              <span>{t('workflow.optional')}</span>
            </div>
            <TextArea
              rows={14}
              value={configuredText(agent, 'system_prompt')}
              oninput={(event: Event) =>
                setConfiguredText(
                  agent,
                  'system_prompt',
                  (event.currentTarget as HTMLTextAreaElement).value
                )}
              placeholder={t('workflow.systemInstructionsPlaceholder')}
              class="prompt-editor font-mono text-xs"
            />
            <p class="text-muted mt-2 text-[10px]">
              {t('workflow.builtInSafetyNote')}
            </p>
          </div>
        {:else if inspectorTab === 'model'}
          <div class="mx-auto grid max-w-4xl gap-5 md:grid-cols-2">
            <div class="setting-card md:col-span-2">
              <div class="section-heading">
                <div>
                  <h3>{t('workflow.languageModel')}</h3>
                  <p>{t('workflow.languageModelDescription')}</p>
                </div>
              </div>
              <div class="grid gap-4 md:grid-cols-[0.7fr_1.3fr]">
                <label class="field-label">
                  {t('agents.provider')}
                  <span class="icon-select">
                    <BrandIcon brand={agent.provider} size={17} />
                    <select
                      class="field"
                      value={agent.provider}
                      onchange={(event) => changeProvider(agent, event)}
                      ><option value="openai">OpenAI</option><option value="anthropic"
                        >Anthropic / Claude</option
                      ><option value="google">Google / Gemini</option></select
                    >
                  </span>
                </label>
                <label class="field-label" for={`model-${agent.role}`}
                  >{t('agents.model')}
                  <div class="flex items-start gap-2">
                    <div class="min-w-0 flex-1">
                      <span class="icon-select">
                        <BrandIcon brand={agent.provider} size={17} />
                        <select
                          id={`model-${agent.role}`}
                          class="field w-full"
                          value={usesManualModel(agent) ? '__manual__' : agent.model}
                          onchange={(event) => changeModel(agent, event)}
                        >
                          <option value="">{t('workflow.selectModel')}</option>
                          {#each availableModels(agent) as model (model.id)}
                            <option value={model.id}>{model.display_name} · {model.id}</option>
                          {/each}
                          <option value="__manual__">{t('workflow.enterModelIdManually')}</option>
                        </select>
                      </span>
                      {#if usesManualModel(agent)}
                        <input
                          class="field mt-2 w-full"
                          bind:value={agent.model}
                          placeholder={t('workflow.enterModelId')}
                          aria-label={t('workflow.enterModelId')}
                        />
                      {/if}
                    </div>
                    <Button
                      disabled={loadingProvider === agent.provider}
                      onclick={() => discoverModels(agent.provider)}
                      >{loadingProvider === agent.provider
                        ? t('common.loading')
                        : t('workflow.discover')}</Button
                    >
                  </div>
                </label>
              </div>
            </div>
            <div class="setting-card">
              <label class="field-label"
                >{t('workflow.inputCost')} <span>{t('workflow.usdPerMillionTokens')}</span><input
                  class="field"
                  type="number"
                  min="0"
                  step="0.000001"
                  value={configuredNumber(agent, 'input_cost_per_million')}
                  oninput={(event) => setConfiguredNumber(agent, 'input_cost_per_million', event)}
                /></label
              >
            </div>
            <div class="setting-card">
              <label class="field-label"
                >{t('workflow.outputCost')} <span>{t('workflow.usdPerMillionTokens')}</span><input
                  class="field"
                  type="number"
                  min="0"
                  step="0.000001"
                  value={configuredNumber(agent, 'output_cost_per_million')}
                  oninput={(event) => setConfiguredNumber(agent, 'output_cost_per_million', event)}
                /></label
              >
            </div>
            <p class="text-muted text-xs md:col-span-2">
              {#if agent.last_run_at}{t('workflow.lastRun', {
                  date: date.format(new Date(agent.last_run_at)),
                  provider: agent.last_provider ?? '',
                  model: agent.last_model ?? '',
                  duration: agent.last_duration_ms ?? 0
                })}{:else}{t('workflow.noModelRunRecorded')}{/if}
            </p>
          </div>
        {:else if inspectorTab === 'runtime'}
          {#if runtimeLoading}
            <div class="mx-auto max-w-4xl space-y-3" aria-busy="true">
              <Skeleton class="h-36 w-full" />
              <Skeleton class="h-12 w-full" />
            </div>
          {:else if agentRuntime}
            {#key agentRuntime.agent_id}
              <AgentRuntimePanel
                runtime={agentRuntime}
                capabilities={modelCapabilities}
                onSave={saveRuntime}
                onReset={resetRuntime}
              />
            {/key}
          {:else}
            <p class="text-muted mx-auto max-w-4xl text-sm">
              Select a concrete workflow Agent to configure runtime inheritance.
            </p>
          {/if}
        {:else}
          <div class="mx-auto grid max-w-5xl gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <div class="setting-card h-fit">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h3 class="text-sm font-semibold">{t('workflow.repositoryContext')}</h3>
                  <p class="text-muted mt-1 text-xs">
                    {t('workflow.repositoryContextDescription')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={repositoryKnowledgeEnabled(agent)}
                  onchange={(event) => setRepositoryKnowledge(agent, event)}
                  aria-label={`Use repository knowledge for ${agent.role}`}
                />
              </div>
            </div>
            <div class="setting-card lg:row-span-2">
              <div class="section-heading">
                <div>
                  <h3>{t('workflow.manualKnowledge')}</h3>
                  <p>{t('workflow.manualKnowledgeDescription')}</p>
                </div>
                <span>{t('workflow.vectorSearch')}</span>
              </div>
              <input
                class="field mb-3"
                bind:value={knowledgeTitle}
                placeholder={t('workflow.knowledgeTitlePlaceholder')}
              />
              <TextArea
                rows={8}
                bind:value={knowledgeContent}
                placeholder={t('workflow.knowledgeContentPlaceholder')}
                class="mb-3 text-xs"
              />
              <Button
                variant="primary"
                disabled={preparingKnowledge || knowledgeContent.trim().length < 20}
                onclick={prepareKnowledge}
                >{preparingKnowledge
                  ? t('workflow.embedding')
                  : t('workflow.embedKnowledge')}</Button
              >
            </div>
            <div class="setting-card">
              <h3 class="mb-3 text-sm font-semibold">
                {t('workflow.storedSources')}
                <span class="text-muted font-normal"
                  >({(knowledge[selectedRole] || []).length})</span
                >
              </h3>
              {#if (knowledge[selectedRole] || []).length}<div class="space-y-2">
                  {#each knowledge[selectedRole] || [] as source (source.id)}<div
                      class="knowledge-item"
                    >
                      <span
                        ><b>{source.title}</b><small
                          >{t('workflow.vectorChunks', { count: source.chunk_count })}</small
                        ></span
                      ><Button size="sm" variant="danger" onclick={() => removeKnowledge(source)}
                        >{t('workflow.delete')}</Button
                      >
                    </div>{/each}
                </div>{:else}<p class="text-muted text-xs">
                  {t('workflow.noManualKnowledge')}
                </p>{/if}
            </div>
          </div>
        {/if}
      </div>
    {/each}
  </section>
</main>

{#if pendingTeamId !== null}
  <ResourceModal
    title="Discard unsaved workflow changes?"
    description="The current Team workflow has changes that have not been saved."
    onClose={() => (pendingTeamId = null)}
  >
    <p class="text-muted text-sm leading-relaxed">
      Switching Teams now will discard your unsaved graph changes. Save the workflow first if you
      want to keep them.
    </p>
    <div class="mt-6 flex justify-end gap-2">
      <Button onclick={() => (pendingTeamId = null)}>Stay here</Button>
      <Button
        variant="primary"
        onclick={() => {
          const nextTeamId = pendingTeamId;
          if (nextTeamId === null) return;
          void switchTeam(nextTeamId).catch((cause) => {
            error = String(cause);
          });
        }}>Discard and switch</Button
      >
    </div>
  </ResourceModal>
{/if}

{#if consoleAgent}
  <TerminalConsole
    agent={consoleAgent}
    nodeId={selectedNodeId}
    onClose={() => (consoleAgent = null)}
  />
{/if}

<style>
  .status-badge {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.2rem 0.45rem;
    color: var(--color-muted);
    font-size: 0.5rem;
    font-weight: 800;
    letter-spacing: 0.1em;
  }
  .status-badge i {
    width: 0.35rem;
    height: 0.35rem;
    border-radius: 50%;
    background: var(--color-muted);
  }
  .status-badge.online {
    border-color: color-mix(in srgb, var(--color-accent) 30%, transparent);
    color: var(--color-accent);
  }
  .status-badge.online i {
    background: var(--color-accent);
    box-shadow: 0 0 7px color-mix(in srgb, var(--color-accent) 70%, transparent);
  }
  .enable-control {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .metrics-strip {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    border-bottom: 1px solid var(--color-line);
    background: var(--color-panel-alt);
  }
  .metrics-strip div {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    border-right: 1px solid var(--color-line);
    padding: 0.75rem 1.25rem;
  }
  .metrics-strip span {
    color: var(--color-muted);
    font-size: 0.5rem;
    font-weight: 800;
    letter-spacing: 0.12em;
  }
  .metrics-strip b {
    color: var(--color-heading);
    font-size: 0.85rem;
  }
  .inspector-tabs {
    display: flex;
    gap: 1.5rem;
    border-bottom: 1px solid var(--color-line);
    padding: 0 1.5rem;
  }
  .inspector-tabs button {
    position: relative;
    padding: 1rem 0 0.85rem;
    color: var(--color-muted);
    font-size: 0.7rem;
    font-weight: 700;
  }
  .inspector-tabs button:hover {
    color: var(--color-heading);
  }
  .inspector-tabs button.active {
    color: var(--color-brand-2);
  }
  .inspector-tabs button.active::after {
    position: absolute;
    right: 0;
    bottom: -1px;
    left: 0;
    height: 2px;
    background: var(--color-brand-2);
    content: '';
  }
  .section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.8rem;
  }
  .section-heading h3 {
    color: var(--color-heading);
    font-size: 0.85rem;
    font-weight: 650;
  }
  .section-heading p {
    margin-top: 0.2rem;
    color: var(--color-muted);
    font-size: 0.68rem;
  }
  .section-heading > span {
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.2rem 0.4rem;
    color: var(--color-muted);
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: 0.1em;
  }
  .setting-card {
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    background: var(--color-panel-alt);
    padding: 1.1rem;
  }
  .field-label {
    display: block;
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .field-label > span {
    float: right;
    color: var(--color-muted);
  }
  .field-label > .icon-select {
    position: relative;
    display: block;
    float: none;
    color: var(--color-heading);
  }
  .icon-select :global(.brand-icon) {
    position: absolute;
    z-index: 1;
    top: 50%;
    left: 0.75rem;
    transform: translateY(-50%);
    pointer-events: none;
  }
  .icon-select .field {
    padding-left: 2.4rem;
  }
  .field {
    display: block;
    width: 100%;
    min-height: 2.65rem;
    margin-top: 0.4rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    padding: 0.65rem 0.75rem;
    color: var(--color-heading);
    outline: none;
    font-size: 0.75rem;
  }
  .field:focus {
    border-color: var(--color-brand);
  }
  .knowledge-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    padding: 0.65rem 0.7rem;
    font-size: 0.7rem;
  }
  .knowledge-item small {
    display: block;
    margin-top: 0.1rem;
    color: var(--color-muted);
    font-size: 0.58rem;
  }
  :global(.prompt-editor) {
    min-height: 280px;
    border-radius: 0.65rem !important;
    line-height: 1.65;
  }
  @media (min-width: 640px) {
    .metrics-strip {
      grid-template-columns: repeat(5, 1fr);
    }
  }
</style>
