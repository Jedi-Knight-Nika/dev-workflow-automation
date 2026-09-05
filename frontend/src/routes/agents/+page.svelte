<script lang="ts">
  import { onMount } from 'svelte';
  import PageHeader from '$lib/PageHeader.svelte';
  import { api } from '$lib/api';
  import type { AgentConfig, ProviderCatalog } from '$lib/types';
  let agents: AgentConfig[] = [];
  let error = '';
  let saved = '';
  let catalogs: Record<string, ProviderCatalog> = {};
  let loadingProvider = '';
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
  async function load() {
    agents = await api<AgentConfig[]>('/agents');
  }
  async function save(agent: AgentConfig) {
    try {
      await api(`/agents/${agent.role}`, {
        method: 'PUT',
        body: JSON.stringify({
          enabled: agent.enabled,
          provider: agent.provider,
          model: agent.model,
          configuration: agent.configuration
        })
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
      catalogs[provider] = await api<ProviderCatalog>(`/providers/${provider}/catalog`);
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
  eyebrow="MODEL ROUTING"
  title="Agents"
  description="Choose the provider and model used by each specialized worker role."
/>
<main class="p-6 md:p-10">
  {#if error}<p class="mb-4 bg-red-950 p-3 text-red-300">{error}</p>{/if}
  <div class="grid gap-4 lg:grid-cols-2">
    {#each agents as agent (agent.role)}<article class="border-line bg-panel border p-5">
        <div class="mb-5 flex items-center justify-between">
          <div>
            <p class="text-accent font-mono text-[10px]">AGENT ROLE</p>
            <h2 class="text-xl font-semibold">{agent.role}</h2>
          </div>
          <div class="flex items-center gap-3">
            <span
              class="font-mono text-[10px] {agent.status === 'RUNNING' || agent.status === 'READY'
                ? 'text-accent'
                : agent.status === 'NEEDS_CONFIGURATION'
                  ? 'text-[#ffbd66]'
                  : 'text-muted'}">{agent.status.replaceAll('_', ' ')}</span
            >
            <input
              type="checkbox"
              bind:checked={agent.enabled}
              aria-label={`Enable ${agent.role}`}
            />
          </div>
        </div>
        <div class="border-line mb-5 grid grid-cols-2 border text-xs sm:grid-cols-5">
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
              class="border-line mt-1.5 block w-full border bg-[#090c0a] p-3 text-white"
              type="number"
              min="0"
              step="0.000001"
              value={configuredNumber(agent, 'input_cost_per_million')}
              oninput={(event) => setConfiguredNumber(agent, 'input_cost_per_million', event)}
            /></label
          >
          <label class="text-muted text-xs"
            >Output $ / 1M tokens<input
              class="border-line mt-1.5 block w-full border bg-[#090c0a] p-3 text-white"
              type="number"
              min="0"
              step="0.000001"
              value={configuredNumber(agent, 'output_cost_per_million')}
              oninput={(event) => setConfiguredNumber(agent, 'output_cost_per_million', event)}
            /></label
          >
        </div>
        <label class="text-muted mb-3 block text-xs"
          >Provider<select
            class="border-line mt-1.5 block w-full border bg-[#090c0a] p-3 text-white"
            bind:value={agent.provider}
            ><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option
            ><option value="google">Google</option></select
          ></label
        >
        <div class="mb-3">
          <div class="flex items-end justify-between gap-3">
            <label class="text-muted text-xs" for={`model-${agent.role}`}>Model</label>
            <button
              class="border-line border px-2 py-1 text-[10px]"
              type="button"
              disabled={loadingProvider === agent.provider}
              onclick={() => discoverModels(agent.provider)}
              >{loadingProvider === agent.provider ? 'Loading…' : 'Discover models'}</button
            >
          </div>
          {#if catalogs[agent.provider]?.models.length}
            <select
              id={`model-${agent.role}`}
              class="border-line mt-1.5 block w-full border bg-[#090c0a] p-3 text-white"
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
              class="border-line mt-1.5 block w-full border bg-[#090c0a] p-3 text-white"
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
        <button
          class="bg-accent cursor-pointer px-4 py-2.5 text-xs font-bold text-[#07100a]"
          onclick={() => save(agent)}
          >{saved === agent.role ? 'Saved' : 'Save configuration'}</button
        >
      </article>{/each}
  </div>
</main>
