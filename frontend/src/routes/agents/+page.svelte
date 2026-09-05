<script lang="ts">
  import { onMount } from 'svelte';
  import { API_URL } from '$lib/api';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import TextArea from '$lib/components/TextArea.svelte';
  import WorkflowCanvas from '$lib/components/workflow/WorkflowCanvas.svelte';
  import TerminalConsole from '$lib/components/workflow/TerminalConsole.svelte';
  import {
    addAgentKnowledge,
    deleteAgentKnowledge,
    discoverProviderModels,
    getWorkflow,
    listAgentKnowledge,
    listAgents,
    saveAgent,
    saveWorkflow
  } from '$lib/services/agents';
  import type { AgentConfig, AgentKnowledge, ProviderCatalog, WorkflowGraph } from '$lib/types';
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
  let selectedNodeId = '';
  let consoleAgent: AgentConfig | null = null;
  let inspectorTab = 'instructions';
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
  function repositoryKnowledgeEnabled(agent: AgentConfig) {
    return agent.configuration.use_repository_knowledge !== false;
  }
  function setRepositoryKnowledge(agent: AgentConfig, event: Event) {
    agent.configuration.use_repository_knowledge = (
      event.currentTarget as HTMLInputElement
    ).checked;
  }
  async function load() {
    [agents, workflow] = await Promise.all([listAgents(), getWorkflow()]);
    const entries = await Promise.all(
      agents.map(async (agent) => [agent.role, await listAgentKnowledge(agent.role)] as const)
    );
    knowledge = Object.fromEntries(entries);
  }
  async function persistWorkflow(graph: WorkflowGraph) {
    try {
      workflow = await saveWorkflow(graph);
      saved = 'WORKFLOW';
      setTimeout(() => (saved = ''), 1500);
    } catch (cause) {
      error = String(cause);
      throw cause;
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
    return () => events.close();
  });
</script>

<PageHeader
  eyebrow="WORKFLOW BUILDER"
  title="Engineering workflow"
  description="Configure the single pipeline, its AI workers, prompts, models, and knowledge access."
/>
<main class="p-4 sm:p-6 md:p-10">
  <ErrorBanner message={error} class="mb-4" />
  {#if workflow}
    <WorkflowCanvas
      {workflow}
      {agents}
      {selectedRole}
      onselect={(role, nodeId) => {
        selectedRole = role;
        selectedNodeId = nodeId;
      }}
      onsave={persistWorkflow}
    />
  {/if}
  <section id="agent-inspector" class="border-line bg-panel overflow-hidden rounded-xl border">
    {#each agents.filter((item) => item.role === selectedRole) as agent (agent.role)}
      <header class="border-line flex flex-wrap items-center gap-4 border-b px-5 py-4 sm:px-6">
        <div class="agent-mark">{agent.role.slice(0, 2)}</div>
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
          <p class="text-muted text-xs">Agent configuration and runtime context</p>
        </div>
        <div class="ml-auto flex items-center gap-3">
          <Button size="sm" variant="ghost" onclick={() => (consoleAgent = agent)}
            >⌘ Live console</Button
          >
          <label class="enable-control">
            <span>{agent.enabled ? 'Enabled' : 'Disabled'}</span>
            <input
              type="checkbox"
              bind:checked={agent.enabled}
              aria-label={`Enable ${agent.role}`}
            />
          </label>
          <Button size="sm" variant="primary" onclick={() => save(agent)}>
            {saved === agent.role ? 'Saved ✓' : 'Save changes'}
          </Button>
        </div>
      </header>

      <div class="metrics-strip">
        <div><span>ACTIVE</span><b>{agent.active_jobs}</b></div>
        <div><span>TOTAL RUNS</span><b>{number.format(agent.total_runs)}</b></div>
        <div><span>INPUT TOKENS</span><b>{number.format(agent.total_input_tokens)}</b></div>
        <div><span>OUTPUT TOKENS</span><b>{number.format(agent.total_output_tokens)}</b></div>
        <div><span>EST. COST</span><b>${agent.total_estimated_cost_usd.toFixed(4)}</b></div>
      </div>

      <nav class="inspector-tabs" aria-label="Agent settings">
        {#each [['instructions', 'Instructions'], ['model', 'Model & cost'], ['knowledge', 'Knowledge']] as tab (tab[0])}
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
                <h3>System instructions</h3>
                <p>Define this agent’s role, boundaries, and expected output.</p>
              </div>
              <span>OPTIONAL</span>
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
              placeholder="Leave blank to use the safe built-in role prompt."
              class="prompt-editor font-mono text-xs"
            />
            <p class="text-muted mt-2 text-[10px]">
              The built-in safety and tool rules remain active around your custom instructions.
            </p>
          </div>
        {:else if inspectorTab === 'model'}
          <div class="mx-auto grid max-w-4xl gap-5 md:grid-cols-2">
            <div class="setting-card md:col-span-2">
              <div class="section-heading">
                <div>
                  <h3>Language model</h3>
                  <p>Provider and exact model used for this role.</p>
                </div>
              </div>
              <div class="grid gap-4 md:grid-cols-[0.7fr_1.3fr]">
                <label class="field-label"
                  >Provider<select class="field" bind:value={agent.provider}
                    ><option value="openai">OpenAI</option><option value="anthropic"
                      >Anthropic</option
                    ><option value="google">Google</option></select
                  ></label
                >
                <label class="field-label" for={`model-${agent.role}`}
                  >Model
                  <div class="flex gap-2">
                    {#if catalogs[agent.provider]?.models.length}
                      <select
                        id={`model-${agent.role}`}
                        class="field flex-1"
                        bind:value={agent.model}
                        ><option value="">Select model</option
                        >{#each catalogs[agent.provider].models as model (model.id)}<option
                            value={model.id}>{model.display_name} · {model.id}</option
                          >{/each}</select
                      >
                    {:else}<input
                        id={`model-${agent.role}`}
                        class="field flex-1"
                        bind:value={agent.model}
                        placeholder="Enter model ID"
                      />{/if}
                    <Button
                      disabled={loadingProvider === agent.provider}
                      onclick={() => discoverModels(agent.provider)}
                      >{loadingProvider === agent.provider ? 'Loading…' : 'Discover'}</Button
                    >
                  </div>
                </label>
              </div>
            </div>
            <div class="setting-card">
              <label class="field-label"
                >Input cost <span>USD / 1M tokens</span><input
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
                >Output cost <span>USD / 1M tokens</span><input
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
              {#if agent.last_run_at}Last run {date.format(new Date(agent.last_run_at))} · {agent.last_provider}/{agent.last_model}
                · {agent.last_duration_ms} ms{:else}No model run recorded yet.{/if}
            </p>
          </div>
        {:else}
          <div class="mx-auto grid max-w-5xl gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <div class="setting-card h-fit">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h3 class="text-sm font-semibold">Repository context</h3>
                  <p class="text-muted mt-1 text-xs">
                    Retrieve relevant indexed source code during runs.
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
                  <h3>Manual knowledge</h3>
                  <p>Add role-specific product context, rules, or examples.</p>
                </div>
                <span>VECTOR SEARCH</span>
              </div>
              <input class="field mb-3" bind:value={knowledgeTitle} placeholder="Knowledge title" />
              <TextArea
                rows={8}
                bind:value={knowledgeContent}
                placeholder="Paste architecture rules, product context, examples, or operating instructions…"
                class="mb-3 text-xs"
              />
              <Button
                variant="primary"
                disabled={preparingKnowledge || knowledgeContent.trim().length < 20}
                onclick={prepareKnowledge}
                >{preparingKnowledge ? 'Embedding…' : 'Embed knowledge'}</Button
              >
            </div>
            <div class="setting-card">
              <h3 class="mb-3 text-sm font-semibold">
                Stored sources <span class="text-muted font-normal"
                  >({(knowledge[selectedRole] || []).length})</span
                >
              </h3>
              {#if (knowledge[selectedRole] || []).length}<div class="space-y-2">
                  {#each knowledge[selectedRole] || [] as source (source.id)}<div
                      class="knowledge-item"
                    >
                      <span
                        ><b>{source.title}</b><small>{source.chunk_count} vector chunks</small
                        ></span
                      ><Button size="sm" variant="danger" onclick={() => removeKnowledge(source)}
                        >Delete</Button
                      >
                    </div>{/each}
                </div>{:else}<p class="text-muted text-xs">
                  No manual knowledge added for this agent.
                </p>{/if}
            </div>
          </div>
        {/if}
      </div>
    {/each}
  </section>
</main>

{#if consoleAgent}
  <TerminalConsole
    agent={consoleAgent}
    nodeId={selectedNodeId}
    onclose={() => (consoleAgent = null)}
  />
{/if}

<style>
  .agent-mark {
    display: grid;
    width: 2.6rem;
    height: 2.6rem;
    place-items: center;
    border: 1px solid rgb(96 165 250 / 35%);
    border-radius: 0.75rem;
    background: linear-gradient(145deg, rgb(37 99 235 / 25%), rgb(79 70 229 / 15%));
    color: #bfdbfe;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.08em;
  }
  .status-badge {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    border: 1px solid #334155;
    border-radius: 999px;
    padding: 0.2rem 0.45rem;
    color: #94a3b8;
    font-size: 0.5rem;
    font-weight: 800;
    letter-spacing: 0.1em;
  }
  .status-badge i {
    width: 0.35rem;
    height: 0.35rem;
    border-radius: 50%;
    background: #64748b;
  }
  .status-badge.online {
    border-color: rgb(52 211 153 / 30%);
    color: #6ee7b7;
  }
  .status-badge.online i {
    background: #34d399;
    box-shadow: 0 0 7px rgb(52 211 153 / 70%);
  }
  .enable-control {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    color: #94a3b8;
    font-size: 0.65rem;
  }
  .metrics-strip {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    border-bottom: 1px solid var(--color-line);
    background: rgb(6 11 19 / 28%);
  }
  .metrics-strip div {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    border-right: 1px solid var(--color-line);
    padding: 0.75rem 1.25rem;
  }
  .metrics-strip span {
    color: #64748b;
    font-size: 0.5rem;
    font-weight: 800;
    letter-spacing: 0.12em;
  }
  .metrics-strip b {
    color: #e2e8f0;
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
    color: #64748b;
    font-size: 0.7rem;
    font-weight: 700;
  }
  .inspector-tabs button:hover {
    color: #cbd5e1;
  }
  .inspector-tabs button.active {
    color: #93c5fd;
  }
  .inspector-tabs button.active::after {
    position: absolute;
    right: 0;
    bottom: -1px;
    left: 0;
    height: 2px;
    background: #60a5fa;
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
    color: #e2e8f0;
    font-size: 0.85rem;
    font-weight: 650;
  }
  .section-heading p {
    margin-top: 0.2rem;
    color: #64748b;
    font-size: 0.68rem;
  }
  .section-heading > span {
    border: 1px solid #334155;
    border-radius: 999px;
    padding: 0.2rem 0.4rem;
    color: #64748b;
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: 0.1em;
  }
  .setting-card {
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    background: rgb(9 15 25 / 35%);
    padding: 1.1rem;
  }
  .field-label {
    display: block;
    color: #94a3b8;
    font-size: 0.65rem;
  }
  .field-label > span {
    float: right;
    color: #64748b;
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
    color: #64748b;
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
