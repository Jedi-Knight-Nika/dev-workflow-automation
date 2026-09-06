<script lang="ts">
  import { Handle, Position, type NodeProps } from '@xyflow/svelte';
  import PixelAgentAvatar from '$lib/components/agents/PixelAgentAvatar.svelte';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';

  type AgentNodeData = {
    displayName: string;
    role: string;
    status: string;
    system: boolean;
    provider: string;
    model: string;
    integrationNames: string[];
    repositoryCount: number;
    modelValidationStatus: string;
    modelValidationMessage: string | null;
    enabled: boolean;
    onMenu?: (event: MouseEvent) => void;
  };

  let { data }: NodeProps = $props();
  const agent = $derived(data as AgentNodeData);

  const statusLabel = $derived(
    agent.status === 'SYSTEM_READY'
      ? 'SYSTEM READY'
      : agent.status === 'NEEDS_VERIFICATION'
        ? 'NEEDS MODEL TEST'
        : agent.status.replaceAll('_', ' ')
  );

  const statusHint = $derived(
    agent.status === 'SYSTEM_READY'
      ? 'Deterministic workflow controller; no AI model is required.'
      : agent.status === 'NEEDS_CONFIGURATION'
        ? 'Choose a provider and model, then save the workflow.'
        : agent.status === 'NEEDS_VERIFICATION'
          ? 'Open this Agent and select Test model.'
          : agent.modelValidationMessage || statusLabel
  );
</script>

<Handle type="target" position={Position.Left} />
<div class="node-shell" class:disabled={!agent.enabled}>
  <PixelAgentAvatar
    seed={`${agent.displayName}:${agent.role}`}
    label={agent.displayName}
    size={36}
  />
  <div class="min-w-0 flex-1">
    <div class="mb-1 flex items-center gap-2">
      <strong class="truncate text-base font-semibold">{agent.displayName}</strong>
      {#if agent.system}<span class="system-pill">CORE</span>{/if}
    </div>
    <div class="flex items-center gap-1.5">
      <span
        class="status-dot"
        class:running={agent.status === 'RUNNING'}
        class:ready={['READY', 'SYSTEM_READY'].includes(agent.status)}
        class:warning={['NEEDS_CONFIGURATION', 'NEEDS_VERIFICATION'].includes(agent.status)}
        class:error={agent.status === 'CONFIGURATION_ERROR'}
        class:off={!agent.enabled}
      ></span>
      <span class="role-name">{agent.role}</span><span class="separator">·</span>
      <span class="text-muted text-[9px] tracking-[0.1em]" title={statusHint}
        >{agent.enabled ? statusLabel : 'DISABLED'}</span
      >
    </div>
    {#if agent.system && agent.role === 'ORCHESTRATOR'}
      <div class="model-row" title={statusHint}>
        <span class="system-mark">◆</span>
        <span class="model-name">Deterministic workflow control</span>
        <span class="validation-label ready-label">READY</span>
      </div>
    {:else}<div class="model-row">
        <span class="provider-mark" title={agent.provider || 'Provider not configured'}>
          <BrandIcon brand={agent.provider} size={13} />
        </span>
        <span class="model-name">{agent.model || 'Model not configured'}</span>
        <span
          class="validation-dot"
          class:available={agent.modelValidationStatus === 'AVAILABLE'}
          class:invalid={['MODEL_NOT_FOUND', 'UNAUTHORIZED', 'ERROR'].includes(
            agent.modelValidationStatus
          )}
          title={agent.modelValidationMessage || agent.modelValidationStatus.replaceAll('_', ' ')}
        ></span>
        <span class="validation-label" title={statusHint}>
          {agent.modelValidationStatus === 'AVAILABLE'
            ? 'READY'
            : agent.model
              ? 'TEST MODEL'
              : 'NOT SET'}
        </span>
      </div>{/if}
    {#if agent.integrationNames.length || agent.repositoryCount}
      <div class="access-row">
        {#each agent.integrationNames.slice(0, 3) as name (name)}
          <span class="integration-mark" title={name}><BrandIcon brand={name} size={12} /></span>
        {/each}
        {#if agent.integrationNames.length > 3}
          <span class="more-count">+{agent.integrationNames.length - 3}</span>
        {/if}
        {#if agent.repositoryCount}
          <span class="project-count" title={`${agent.repositoryCount} projects with RAG access`}>
            ◇ {agent.repositoryCount}
            {agent.repositoryCount === 1 ? 'project' : 'projects'}
          </span>
        {/if}
      </div>
    {/if}
  </div>
  <button
    class="menu-hint nodrag"
    type="button"
    aria-label={`Open ${agent.displayName} actions`}
    onclick={(event) => {
      event.stopPropagation();
      agent.onMenu?.(event);
    }}>•••</button
  >
</div>
<Handle type="source" position={Position.Right} />

<style>
  .node-shell {
    display: flex;
    min-width: 245px;
    align-items: center;
    gap: 0.75rem;
    padding: 0.8rem 0.85rem;
  }
  .system-pill {
    border: 1px solid color-mix(in srgb, var(--color-brand) 35%, transparent);
    border-radius: 999px;
    padding: 0.1rem 0.32rem;
    color: var(--color-brand);
    font-size: 0.45rem;
    font-weight: 800;
    letter-spacing: 0.12em;
  }
  .status-dot {
    height: 0.4rem;
    width: 0.4rem;
    border-radius: 999px;
    background: var(--color-muted);
  }
  .status-dot.running {
    background: var(--color-accent);
    box-shadow: 0 0 9px color-mix(in srgb, var(--color-accent) 75%, transparent);
  }
  .status-dot.ready {
    background: var(--color-accent);
  }
  .status-dot.warning {
    background: var(--color-warning);
  }
  .status-dot.error {
    background: var(--color-danger);
  }
  .status-dot.off {
    background: var(--color-danger);
    box-shadow: none;
  }
  .node-shell.disabled {
    opacity: 0.5;
    filter: saturate(0.35);
  }
  .role-name {
    color: var(--color-brand-2);
    font-size: 0.55rem;
    font-weight: 800;
    letter-spacing: 0.12em;
  }
  .separator {
    color: var(--color-muted);
    font-size: 0.6rem;
  }
  .model-row {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.45rem;
    border-top: 1px solid var(--color-line);
    padding-top: 0.42rem;
  }
  .provider-mark {
    display: grid;
    width: 1.05rem;
    height: 1.05rem;
    flex: none;
    place-items: center;
    border: 1px solid var(--color-line);
    border-radius: 0.3rem;
    background: var(--color-panel-alt);
    color: var(--color-brand-2);
    font-size: 0.45rem;
    font-weight: 900;
  }
  .system-mark {
    color: var(--color-brand);
    font-size: 0.7rem;
  }
  .model-name {
    overflow: hidden;
    color: var(--color-muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.55rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .validation-dot {
    margin-left: auto;
    width: 0.42rem;
    height: 0.42rem;
    flex: none;
    border-radius: 50%;
    background: var(--color-muted);
  }
  .validation-dot.available {
    background: var(--color-accent);
    box-shadow: 0 0 6px color-mix(in srgb, var(--color-accent) 65%, transparent);
  }
  .validation-dot.invalid {
    background: var(--color-danger);
    box-shadow: 0 0 6px color-mix(in srgb, var(--color-danger) 55%, transparent);
  }
  .validation-label {
    max-width: 4.5rem;
    overflow: hidden;
    color: var(--color-muted);
    font-size: 0.45rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ready-label {
    margin-left: auto;
    color: var(--color-accent);
  }
  .access-row {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    margin-top: 0.4rem;
  }
  .integration-mark {
    display: grid;
    min-width: 1.18rem;
    height: 1.18rem;
    place-items: center;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 30%, transparent);
    border-radius: 0.35rem;
    background: color-mix(in srgb, var(--color-brand-2) 12%, transparent);
    padding: 0 0.18rem;
    color: var(--color-brand-2);
    font-size: 0.43rem;
    font-weight: 900;
  }
  .more-count {
    color: var(--color-muted);
    font-size: 0.5rem;
  }
  .project-count {
    margin-left: 0.2rem;
    border-left: 1px solid var(--color-line);
    padding-left: 0.45rem;
    color: var(--color-muted);
    font-size: 0.5rem;
  }
  .menu-hint {
    border: 0;
    border-radius: 0.35rem;
    background: transparent;
    padding: 0.25rem;
    color: var(--color-muted);
    font-size: 0.75rem;
    letter-spacing: 0.08em;
  }
  .menu-hint:hover {
    background: color-mix(in srgb, var(--color-line) 45%, transparent);
    color: var(--color-heading);
  }
</style>
