<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Button from '$lib/components/Button.svelte';
  import ErrorBanner from '$lib/components/ErrorBanner.svelte';
  import Card from '$lib/components/Card.svelte';
  import TextArea from '$lib/components/TextArea.svelte';
  import WorkflowCanvas from '$lib/components/workflow/WorkflowCanvas.svelte';
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
      {selectedRole}
      onselect={(role) => (selectedRole = role)}
      onsave={persistWorkflow}
    />
  {/if}
  <div>
    {#each agents.filter((item) => item.role === selectedRole) as agent, index (agent.role)}<Card
        hover
        class="motion-safe:animate-fade-in-up"
        style="animation-delay: {index * 60}ms"
      >
        <div class="mb-5 flex items-center justify-between">
          <div>
            <p class="text-brand font-mono text-[10px]">AGENT ROLE</p>
            <h2 class="text-xl font-semibold">{agent.role}</h2>
          </div>
          <div class="flex items-center gap-3">
            <span
              class="font-mono text-[10px] {agent.status === 'RUNNING' || agent.status === 'READY'
                ? 'text-accent'
                : agent.status === 'NEEDS_CONFIGURATION'
                  ? 'text-warning'
                  : 'text-muted'}">{agent.status.replaceAll('_', ' ')}</span
            >
            <input
              type="checkbox"
              bind:checked={agent.enabled}
              aria-label={`Enable ${agent.role}`}
            />
          </div>
        </div>
        <div
          class="border-line mb-5 grid grid-cols-2 overflow-hidden rounded-lg border text-xs sm:grid-cols-5"
        >
          <div class="border-line border-r p-3">
            <b class="block text-base">{agent.active_jobs}</b><span class="text-muted">Active</span>
          </div>
          <div class="border-line border-r p-3">
            <b class="block text-base">{number.format(agent.total_runs)}</b><span class="text-muted"
              >Runs</span
            >
          </div>
          <div class="border-line border-r p-3">
            <b class="block text-base">{number.format(agent.total_input_tokens)}</b><span
              class="text-muted">Input tokens</span
            >
          </div>
          <div class="p-3">
            <b class="block text-base">{number.format(agent.total_output_tokens)}</b><span
              class="text-muted">Output tokens</span
            >
          </div>
          <div class="border-line col-span-2 border-t p-3 sm:col-span-1 sm:border-l sm:border-t-0">
            <b class="block text-base">${agent.total_estimated_cost_usd.toFixed(4)}</b><span
              class="text-muted">Estimated</span
            >
          </div>
        </div>
        <div class="mb-4 grid grid-cols-2 gap-3">
          <label class="text-muted text-xs"
            >Input $ / 1M tokens<input
              class="border-line mt-1.5 block w-full rounded-md border bg-input p-3 text-heading"
              type="number"
              min="0"
              step="0.000001"
              value={configuredNumber(agent, 'input_cost_per_million')}
              oninput={(event) => setConfiguredNumber(agent, 'input_cost_per_million', event)}
            /></label
          >
          <label class="text-muted text-xs"
            >Output $ / 1M tokens<input
              class="border-line mt-1.5 block w-full rounded-md border bg-input p-3 text-heading"
              type="number"
              min="0"
              step="0.000001"
              value={configuredNumber(agent, 'output_cost_per_million')}
              oninput={(event) => setConfiguredNumber(agent, 'output_cost_per_million', event)}
            /></label
          >
        </div>
        <div class="border-line mb-4 rounded-lg border p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <strong class="text-sm">Repository knowledge</strong>
              <p class="text-muted text-[10px]">Retrieve relevant indexed code for this role.</p>
            </div>
            <input
              type="checkbox"
              checked={repositoryKnowledgeEnabled(agent)}
              onchange={(event) => setRepositoryKnowledge(agent, event)}
              aria-label={`Use repository knowledge for ${agent.role}`}
            />
          </div>
        </div>
        <TextArea
          label="System prompt"
          rows={8}
          value={configuredText(agent, 'system_prompt')}
          oninput={(event: Event) =>
            setConfiguredText(
              agent,
              'system_prompt',
              (event.currentTarget as HTMLTextAreaElement).value
            )}
          placeholder="Leave blank to use the safe built-in role prompt."
          class="mb-4 font-mono text-xs"
        />
        <div class="border-line mb-4 rounded-lg border p-4">
          <div class="mb-3">
            <strong class="text-sm">Manual role knowledge</strong>
            <p class="text-muted text-[10px]">
              Text is chunked and vector-embedded for this role only. It is retrieved during runs.
            </p>
          </div>
          <input
            class="border-line mb-2 block w-full rounded-md border bg-input p-3 text-heading"
            bind:value={knowledgeTitle}
            placeholder="Knowledge title"
          />
          <TextArea
            rows={6}
            bind:value={knowledgeContent}
            placeholder="Paste architecture rules, product context, examples, or operating instructions…"
            class="mb-2 text-xs"
          />
          <Button
            size="sm"
            disabled={preparingKnowledge || knowledgeContent.trim().length < 20}
            onclick={prepareKnowledge}
          >
            {preparingKnowledge ? 'Embedding…' : 'Embed knowledge'}
          </Button>
          {#if (knowledge[selectedRole] || []).length}
            <div class="mt-3 space-y-2">
              {#each knowledge[selectedRole] || [] as source (source.id)}
                <div
                  class="border-line flex items-center justify-between rounded border p-2 text-xs"
                >
                  <span><b>{source.title}</b> · {source.chunk_count} chunks</span>
                  <Button size="sm" variant="ghost" onclick={() => removeKnowledge(source)}
                    >Delete</Button
                  >
                </div>
              {/each}
            </div>
          {/if}
        </div>
        <label class="text-muted mb-3 block text-xs"
          >Provider<select
            class="border-line mt-1.5 block w-full rounded-md border bg-input p-3 text-heading"
            bind:value={agent.provider}
            ><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option
            ><option value="google">Google</option></select
          ></label
        >
        <div class="mb-3">
          <div class="flex items-end justify-between gap-3">
            <label class="text-muted text-xs" for={`model-${agent.role}`}>Model</label>
            <Button
              size="sm"
              disabled={loadingProvider === agent.provider}
              onclick={() => discoverModels(agent.provider)}
              >{loadingProvider === agent.provider ? 'Loading…' : 'Discover models'}</Button
            >
          </div>
          {#if catalogs[agent.provider]?.models.length}
            <select
              id={`model-${agent.role}`}
              class="border-line mt-1.5 block w-full rounded-md border bg-input p-3 text-heading"
              bind:value={agent.model}
            >
              <option value="">Select model</option>
              {#each catalogs[agent.provider].models as model (model.id)}
                <option value={model.id}>{model.display_name} · {model.id}</option>
              {/each}
            </select>
          {:else}
            <input
              id={`model-${agent.role}`}
              class="border-line mt-1.5 block w-full rounded-md border bg-input p-3 text-heading"
              bind:value={agent.model}
              placeholder="Discover or enter model ID"
            />
          {/if}
        </div>
        <div class="text-muted mb-4 text-xs">
          {#if agent.last_run_at}
            Last run {date.format(new Date(agent.last_run_at))} · {agent.last_provider}/{agent.last_model}
            · {agent.last_duration_ms} ms
          {:else}No model run recorded yet.{/if}
        </div>
        <Button variant="primary" class="w-full" onclick={() => save(agent)}
          >{saved === agent.role ? 'Saved' : 'Save configuration'}</Button
        >
      </Card>{/each}
  </div>
</main>
