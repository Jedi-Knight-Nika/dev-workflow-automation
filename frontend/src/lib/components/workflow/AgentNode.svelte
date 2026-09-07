<script lang="ts">
  import { resolve } from '$app/paths';
  import { Handle, Position, type NodeProps } from '@xyflow/svelte';
  import PixelAgentAvatar from '$lib/components/agents/PixelAgentAvatar.svelte';
  import BrandIcon from '$lib/components/resources/BrandIcon.svelte';

  type AgentNodeData = {
    displayName: string;
    role: string;
    status: string;
    queuedJobs: number;
    activeJobs: number;
    currentJobAction: string | null;
    taskId: string | null;
    taskTitle: string | null;
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

  const roleIcon = $derived(
    agent.role === 'ORCHESTRATOR'
      ? '◎'
      : agent.role === 'THINKER'
        ? '◇'
        : agent.role === 'EXECUTOR'
          ? '</>'
          : agent.role === 'REVIEWER'
            ? '✓'
            : agent.role === 'TESTER'
              ? 'T'
              : 'AI'
  );
</script>

<Handle
  type="target"
  position={Position.Left}
  class={agent.status === 'RUNNING'
    ? 'handle-running'
    : agent.queuedJobs > 0
      ? 'handle-queued'
      : agent.status === 'CONFIGURATION_ERROR'
        ? 'handle-blocked'
        : ''}
/>
<div class="node-shell" class:disabled={!agent.enabled}>
  <div class="worker-avatar" title={`${agent.role.replaceAll('_', ' ')} worker`}>
    <PixelAgentAvatar
      seed={`${agent.displayName}:${agent.role}`}
      label={agent.displayName}
      size={40}
    />
    <span class="role-icon" aria-hidden="true">{roleIcon}</span>
  </div>
  <div class="min-w-0 flex-1">
    <div class="mb-1 flex items-center gap-2">
      <strong class="truncate text-base font-semibold">{agent.displayName}</strong>
      {#if agent.system}<span class="system-pill">CORE</span>{/if}
    </div>
    <div class="node-meta">
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
    {#if agent.status === 'RUNNING' || agent.queuedJobs > 0}
      <div class="activity-card" class:active={agent.status === 'RUNNING'}>
        <div class="activity-heading">
          <span class="activity-pulse"></span>
          <strong>{agent.status === 'RUNNING' ? 'WORKING NOW' : 'QUEUED'}</strong>
          <span>{agent.currentJobAction?.replaceAll('_', ' ') || 'Waiting for execution'}</span>
          {#if agent.queuedJobs > 1}<b>+{agent.queuedJobs - 1}</b>{/if}
        </div>
        {#if agent.taskId}
          <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
          <a
            class="task-summary nodrag"
            href={resolve('/tasks/[id]', { id: agent.taskId })}
            title={agent.taskTitle || `Task ${agent.taskId}`}
            onclick={(event) => event.stopPropagation()}
          >
            <span aria-hidden="true">▱</span>
            <span>
              <small>Current task</small>
              <b>{agent.taskTitle || `Task ${agent.taskId.slice(0, 8)}`}</b>
            </span>
            <i aria-hidden="true">→</i>
          </a>
        {/if}
      </div>
    {/if}
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
<Handle
  type="source"
  position={Position.Right}
  class={agent.status === 'RUNNING'
    ? 'handle-running'
    : agent.queuedJobs > 0
      ? 'handle-queued'
      : agent.status === 'CONFIGURATION_ERROR'
        ? 'handle-blocked'
        : ''}
/>

<style>
  :global(.svelte-flow__handle.handle-running) {
    background: var(--color-brand-2);
    box-shadow: 0 0 9px color-mix(in srgb, var(--color-brand-2) 80%, transparent);
  }
  :global(.svelte-flow__handle.handle-queued) {
    background: var(--color-warning);
    box-shadow: 0 0 7px color-mix(in srgb, var(--color-warning) 65%, transparent);
  }
  :global(.svelte-flow__handle.handle-blocked) {
    background: var(--color-danger);
  }
  .node-shell {
    display: flex;
    min-width: 245px;
    align-items: center;
    gap: 0.75rem;
    padding: 0.8rem 0.85rem;
  }
  .worker-avatar {
    position: relative;
    flex: none;
    align-self: flex-start;
  }
  .role-icon {
    position: absolute;
    right: -0.28rem;
    bottom: -0.22rem;
    display: grid;
    min-width: 1.15rem;
    height: 1.15rem;
    place-items: center;
    border: 2px solid var(--color-panel-alt);
    border-radius: 0.38rem;
    background: color-mix(in srgb, var(--color-brand-2) 18%, var(--color-panel));
    color: var(--color-brand-2);
    font: 800 0.48rem/1 var(--font-mono);
    box-shadow: 0 3px 9px rgb(0 0 0 / 45%);
  }
  .node-shell strong {
    color: var(--color-heading);
    text-shadow: 0 1px 10px rgb(0 0 0 / 35%);
  }
  .node-meta {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 0.38rem;
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
    gap: 0.4rem;
    margin-top: 0.45rem;
    border: 1px solid color-mix(in srgb, var(--color-line) 82%, transparent);
    border-radius: 0.42rem;
    background: color-mix(in srgb, var(--color-surface) 48%, transparent);
    padding: 0.38rem 0.42rem;
  }
  .activity-card {
    display: grid;
    min-width: 0;
    gap: 0.42rem;
    margin-top: 0.45rem;
    border: 1px solid color-mix(in srgb, var(--color-warning) 24%, var(--color-line));
    border-radius: 0.48rem;
    background: color-mix(in srgb, var(--color-warning) 10%, transparent);
    padding: 0.4rem;
    color: var(--color-warning);
  }
  .activity-card.active {
    border-color: color-mix(in srgb, var(--color-brand-2) 28%, var(--color-line));
    background: color-mix(in srgb, var(--color-brand-2) 10%, transparent);
    color: var(--color-brand-2);
  }
  .activity-heading {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.48rem;
  }
  .activity-heading > span:not(.activity-pulse) {
    overflow: hidden;
    color: var(--color-muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .activity-heading > b {
    margin-left: auto;
  }
  .task-summary {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.42rem;
    border-top: 1px solid color-mix(in srgb, currentColor 16%, transparent);
    padding-top: 0.4rem;
    color: var(--color-text);
  }
  .task-summary > span:first-child {
    color: var(--color-brand-2);
    font-size: 0.8rem;
  }
  .task-summary > span:nth-child(2) {
    display: grid;
    min-width: 0;
    gap: 0.08rem;
  }
  .task-summary small {
    color: var(--color-muted);
    font-size: 0.43rem;
    font-weight: 750;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .task-summary b {
    overflow: hidden;
    color: var(--color-text);
    font-size: 0.58rem;
    font-weight: 650;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .task-summary i {
    color: var(--color-brand-2);
    font-size: 0.7rem;
    font-style: normal;
  }
  .task-summary:hover b {
    color: var(--color-heading);
  }
  .activity-pulse {
    width: 0.36rem;
    height: 0.36rem;
    flex: none;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 6px currentColor;
    animation: activity-pulse 1.35s ease-in-out infinite;
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
    color: color-mix(in srgb, var(--color-text) 82%, var(--color-muted));
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
  @keyframes activity-pulse {
    50% {
      opacity: 0.55;
      transform: scale(1.45);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .activity-pulse {
      animation: none;
    }
  }
</style>
