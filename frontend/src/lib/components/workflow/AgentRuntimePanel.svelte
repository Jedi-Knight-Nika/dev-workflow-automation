<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import type { AgentRuntimeView, ModelCapabilities } from '$lib/types';

  let {
    runtime,
    capabilities,
    onSave,
    onReset
  }: {
    runtime: AgentRuntimeView;
    capabilities: ModelCapabilities | null;
    onSave: (overrides: Record<string, unknown>) => Promise<void>;
    onReset: () => Promise<void>;
  } = $props();

  let draft = $state<Record<string, unknown>>({});
  let loadedAgentId = $state('');
  let saving = $state(false);

  $effect(() => {
    if (loadedAgentId !== runtime.agent_id) {
      loadedAgentId = runtime.agent_id;
      draft = { ...runtime.overrides };
    }
  });

  function value(key: string): string | number {
    const current = draft[key] ?? runtime.effective[key as keyof typeof runtime.effective];
    return typeof current === 'number' || typeof current === 'string' ? current : '';
  }

  function source(key: string): string {
    return key in draft ? 'Agent override' : 'Inherited from Role';
  }

  function update(key: string, next: string | number | null) {
    draft[key] = next;
    draft = { ...draft };
  }

  function clearOverride(key: string) {
    delete draft[key];
    draft = { ...draft };
  }

  async function save() {
    saving = true;
    try {
      await onSave(draft);
    } finally {
      saving = false;
    }
  }

  async function reset() {
    saving = true;
    try {
      await onReset();
      draft = {};
    } finally {
      saving = false;
    }
  }
</script>

{#snippet sourceLabel(key: string)}
  <small>
    {source(key)}
    {#if key in draft}
      · <button type="button" onclick={() => clearOverride(key)}>Reset</button>
    {/if}
  </small>
{/snippet}

<div class="mx-auto max-w-4xl space-y-5">
  <div class="setting-card">
    <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold">Effective runtime</h3>
        <p class="text-muted mt-1 text-xs">
          Role defaults with explicit overrides for {runtime.role_name}.
        </p>
      </div>
      <div class="flex gap-2">
        <Button size="sm" variant="ghost" disabled={saving} onclick={reset}>Reset to Role</Button>
        <Button size="sm" variant="primary" disabled={saving} onclick={save}
          >{saving ? 'Saving…' : 'Save runtime'}</Button
        >
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-2">
      <label class="field-label"
        >Reasoning {@render sourceLabel('reasoning_level')}<select
          class="field"
          value={value('reasoning_level')}
          disabled={runtime.override_policy.reasoning_level === 'LOCKED'}
          onchange={(event) =>
            update('reasoning_level', (event.currentTarget as HTMLSelectElement).value)}
        >
          {#each capabilities?.reasoning_levels ?? ['PROVIDER_DEFAULT'] as level (level)}
            <option value={level}>{level.replaceAll('_', ' ')}</option>
          {/each}
        </select></label
      >
      <label class="field-label"
        >Context strategy {@render sourceLabel('context_strategy')}<select
          class="field"
          value={value('context_strategy')}
          disabled={runtime.override_policy.context_strategy === 'LOCKED'}
          onchange={(event) =>
            update('context_strategy', (event.currentTarget as HTMLSelectElement).value)}
        >
          {#each ['MINIMAL', 'BALANCED', 'DEEP'] as strategy (strategy)}
            <option value={strategy}>{strategy}</option>
          {/each}
        </select></label
      >
      <label class="field-label"
        >Maximum tool calls {@render sourceLabel('max_tool_calls')}<input
          class="field"
          type="number"
          min="1"
          max="200"
          value={value('max_tool_calls')}
          disabled={runtime.override_policy.max_tool_calls === 'LOCKED'}
          oninput={(event) =>
            update('max_tool_calls', Number((event.currentTarget as HTMLInputElement).value))}
        /></label
      >
      <label class="field-label"
        >Job timeout (seconds) {@render sourceLabel('job_timeout_seconds')}<input
          class="field"
          type="number"
          min="60"
          max="43200"
          value={value('job_timeout_seconds')}
          disabled={runtime.override_policy.job_timeout_seconds === 'LOCKED'}
          oninput={(event) =>
            update('job_timeout_seconds', Number((event.currentTarget as HTMLInputElement).value))}
        /></label
      >
      <label class="field-label"
        >Maximum output tokens {@render sourceLabel('max_output_tokens')}<input
          class="field"
          type="number"
          min="256"
          max={capabilities?.max_output_tokens ?? 1000000}
          value={value('max_output_tokens')}
          disabled={runtime.override_policy.max_output_tokens === 'LOCKED'}
          oninput={(event) =>
            update('max_output_tokens', Number((event.currentTarget as HTMLInputElement).value))}
        /></label
      >
      {#if capabilities?.temperature_supported}
        <label class="field-label"
          >Temperature {@render sourceLabel('temperature')}<input
            class="field"
            type="number"
            min="0"
            max="2"
            step="0.1"
            value={value('temperature')}
            disabled={runtime.override_policy.temperature === 'LOCKED'}
            oninput={(event) =>
              update('temperature', Number((event.currentTarget as HTMLInputElement).value))}
          /></label
        >
      {:else}
        <div class="border-line rounded-lg border p-3">
          <p class="text-sm font-medium">Temperature</p>
          <p class="text-muted mt-1 text-xs">Unavailable for the selected model.</p>
        </div>
      {/if}
    </div>
  </div>

  <div class="text-muted grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
    <span>Provider: <b class="text-heading">{runtime.effective.provider}</b></span>
    <span>Model: <b class="text-heading">{runtime.effective.model || 'Not configured'}</b></span>
    <span>Agent config: <b class="text-heading">v{runtime.versions.agent}</b></span>
    <span>Role config: <b class="text-heading">v{runtime.versions.role}</b></span>
    <span>Capabilities: <b class="text-heading">{runtime.versions.capabilities}</b></span>
    <span>Strategy: <b class="text-heading">{runtime.versions.strategy}</b></span>
    <span class="sm:col-span-2 lg:col-span-2"
      >Snapshot: <b class="text-heading font-mono">{runtime.effective_hash.slice(0, 12)}</b></span
    >
  </div>
</div>

<style>
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
  .field-label small {
    float: right;
    font-size: 0.6rem;
  }
  .field-label small button {
    color: var(--color-brand-2);
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
  .field:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
</style>
