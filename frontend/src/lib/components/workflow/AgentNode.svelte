<script lang="ts">
  import { Handle, Position, type NodeProps } from '@xyflow/svelte';

  type AgentNodeData = {
    displayName: string;
    role: string;
    status: string;
    system: boolean;
  };

  let { data }: NodeProps = $props();
  const agent = $derived(data as AgentNodeData);
  const initials = $derived(agent.displayName.slice(0, 2).toUpperCase());
</script>

<Handle type="target" position={Position.Left} />
<div class="node-shell">
  <div class="avatar" class:system={agent.system}>{initials}</div>
  <div class="min-w-0 flex-1">
    <div class="mb-1 flex items-center gap-2">
      <strong class="truncate text-sm font-semibold">{agent.displayName}</strong>
      {#if agent.system}<span class="system-pill">CORE</span>{/if}
    </div>
    <div class="flex items-center gap-1.5">
      <span class="status-dot" class:running={agent.status === 'RUNNING'}></span>
      <span class="text-[9px] tracking-[0.12em] text-slate-400">
        {agent.status.replaceAll('_', ' ')}
      </span>
    </div>
  </div>
  <span class="menu-hint" aria-hidden="true">•••</span>
</div>
<Handle type="source" position={Position.Right} />

<style>
  .node-shell {
    display: flex;
    min-width: 218px;
    align-items: center;
    gap: 0.75rem;
    padding: 0.8rem 0.85rem;
  }
  .avatar {
    display: grid;
    height: 2.25rem;
    width: 2.25rem;
    flex: none;
    place-items: center;
    border: 1px solid rgb(96 165 250 / 35%);
    border-radius: 0.7rem;
    background: linear-gradient(145deg, rgb(37 99 235 / 25%), rgb(79 70 229 / 15%));
    color: #bfdbfe;
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.06em;
  }
  .avatar.system {
    border-color: rgb(167 139 250 / 45%);
    background: linear-gradient(145deg, rgb(124 58 237 / 28%), rgb(79 70 229 / 18%));
    color: #ddd6fe;
  }
  .system-pill {
    border: 1px solid rgb(167 139 250 / 35%);
    border-radius: 999px;
    padding: 0.1rem 0.32rem;
    color: #c4b5fd;
    font-size: 0.45rem;
    font-weight: 800;
    letter-spacing: 0.12em;
  }
  .status-dot {
    height: 0.4rem;
    width: 0.4rem;
    border-radius: 999px;
    background: #64748b;
  }
  .status-dot.running {
    background: #34d399;
    box-shadow: 0 0 9px rgb(52 211 153 / 75%);
  }
  .menu-hint {
    color: #64748b;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
  }
</style>
