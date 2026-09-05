<script lang="ts">
  import { untrack } from 'svelte';
  import {
    Background,
    BackgroundVariant,
    Controls,
    MarkerType,
    MiniMap,
    SvelteFlow,
    addEdge,
    type Connection,
    type Edge,
    type Node
  } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';
  import type { AgentConfig, WorkflowGraph } from '$lib/types';
  import Button from '$lib/components/Button.svelte';
  import AgentNode from './AgentNode.svelte';

  let {
    workflow,
    agents,
    selectedRole,
    onselect,
    onsave
  }: {
    workflow: WorkflowGraph;
    agents: AgentConfig[];
    selectedRole: string;
    onselect: (role: string, nodeId: string) => void;
    onsave: (graph: WorkflowGraph) => Promise<void>;
  } = $props();

  type CanvasData = {
    label: string;
    displayName: string;
    role: string;
    status: string;
    system: boolean;
    activationPolicy: string;
    batchWindowSeconds: number;
  };
  type CanvasNode = Node<CanvasData>;
  const initialWorkflow = untrack(() => workflow);
  let nodes = $state<CanvasNode[]>(
    initialWorkflow.nodes.map((node) => ({
      id: node.id,
      position: { x: node.position_x, y: node.position_y },
      data: {
        label: node.label,
        displayName: node.label,
        role: node.role,
        status: 'UNCONFIGURED',
        system: node.role === 'ORCHESTRATOR' || node.role === 'DELIVERER',
        activationPolicy: node.activation_policy,
        batchWindowSeconds: node.batch_window_seconds
      },
      deletable: node.role !== 'ORCHESTRATOR' && node.role !== 'DELIVERER',
      class: node.role === selectedRole ? 'workflow-node selected' : 'workflow-node',
      type: 'agent'
    }))
  );
  let edges = $state<Edge[]>(
    initialWorkflow.edges.map((edge) => ({
      id: edge.id,
      source: edge.source_node_id,
      target: edge.target_node_id,
      label: edge.outcome,
      type: 'smoothstep',
      animated: true,
      markerEnd: MarkerType.ArrowClosed,
      data: { outcome: edge.outcome, required: edge.required }
    }))
  );
  let saving = $state(false);
  let dirty = $state(false);
  let selectedNodeId = $state('');
  let selectedEdgeId = $state('');
  let nodeMenu = $state<{ x: number; y: number; nodeId: string } | null>(null);
  let addMenuOpen = $state(false);
  const nodeTypes = { agent: AgentNode };
  const availableRoles = ['INTAKE', 'THINKER', 'EXECUTOR', 'REVIEWER', 'TESTER'];

  $effect(() => {
    const statuses = new Map(agents.map((agent) => [agent.role, agent.status]));
    nodes = untrack(() => nodes).map((node) => {
      const status = node.data.system ? 'SYSTEM' : statuses.get(node.data.role) || 'UNCONFIGURED';
      return {
        ...node,
        data: {
          ...node.data,
          status
        },
        class: `workflow-node ${status === 'RUNNING' ? 'running' : ''} ${node.data.role === selectedRole ? 'selected' : ''}`
      };
    });
  });

  function selectNode(node: CanvasNode, event?: MouseEvent) {
    selectedNodeId = node.id;
    selectedEdgeId = '';
    onselect(node.data.role, node.id);
    if (event) {
      nodeMenu = { x: event.clientX, y: event.clientY, nodeId: node.id };
    }
    addMenuOpen = false;
  }

  function editSelectedNode() {
    const node = nodes.find((item) => item.id === nodeMenu?.nodeId);
    if (node) onselect(node.data.role, node.id);
    nodeMenu = null;
    document
      .getElementById('agent-inspector')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function removeNode(nodeId: string) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node || node.data.system) return;
    nodes = nodes.filter((item) => item.id !== nodeId);
    edges = edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
    selectedNodeId = '';
    nodeMenu = null;
    dirty = true;
  }

  function setActivationPolicy(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    nodes = nodes.map((node) =>
      node.id === selectedNodeId
        ? { ...node, data: { ...node.data, activationPolicy: value } }
        : node
    );
    dirty = true;
  }

  function setEdgeOutcome(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    edges = edges.map((edge) =>
      edge.id === selectedEdgeId
        ? { ...edge, label: value, data: { ...edge.data, outcome: value } }
        : edge
    );
    dirty = true;
  }

  function removeSelectedEdge() {
    edges = edges.filter((edge) => edge.id !== selectedEdgeId);
    selectedEdgeId = '';
    dirty = true;
  }

  function connect(connection: Connection) {
    edges = addEdge(
      {
        ...connection,
        id: crypto.randomUUID(),
        type: 'smoothstep',
        animated: true,
        markerEnd: MarkerType.ArrowClosed,
        label: 'success',
        data: { outcome: 'success', required: true }
      },
      edges
    );
    dirty = true;
  }

  function addRole(role: string) {
    if (nodes.some((node) => node.data.role === role)) {
      const existing = nodes.find((node) => node.data.role === role);
      if (existing) onselect(role, existing.id);
      return;
    }
    nodes = [
      ...nodes,
      {
        id: crypto.randomUUID(),
        position: { x: 420 + nodes.length * 45, y: 280 + (nodes.length % 3) * 110 },
        data: {
          label: role[0] + role.slice(1).toLowerCase(),
          displayName: role[0] + role.slice(1).toLowerCase(),
          role,
          status: agents.find((agent) => agent.role === role)?.status || 'UNCONFIGURED',
          system: false,
          activationPolicy: 'any',
          batchWindowSeconds: 0
        },
        deletable: true,
        class: 'workflow-node',
        type: 'agent'
      }
    ];
    onselect(role, nodes[nodes.length - 1].id);
    dirty = true;
  }

  async function persist() {
    saving = true;
    const canvasNodes = nodes;
    const nodeIds = new Set(canvasNodes.map((node) => node.id));
    const graph: WorkflowGraph = {
      version: workflow.version,
      nodes: canvasNodes.map((node) => ({
        id: node.id,
        role: node.data.role,
        label: node.data.label,
        position_x: node.position.x,
        position_y: node.position.y,
        enabled: true,
        activation_policy: node.data.activationPolicy,
        batch_window_seconds: node.data.batchWindowSeconds
      })),
      edges: edges
        .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
        .map((edge) => ({
          id: edge.id,
          source_node_id: edge.source,
          target_node_id: edge.target,
          outcome: String(edge.data?.outcome || 'success'),
          required: edge.data?.required !== false
        }))
    };
    try {
      await onsave(graph);
      dirty = false;
    } finally {
      saving = false;
    }
  }
</script>

<section class="border-line bg-panel mb-6 overflow-hidden rounded-xl border">
  <div class="border-line flex min-h-16 flex-wrap items-center gap-3 border-b px-4 py-3">
    <div class="relative">
      <button class="add-button" type="button" onclick={() => (addMenuOpen = !addMenuOpen)}>
        <span class="text-lg leading-none">+</span> Add agent
        <span class="text-[9px] opacity-60">▼</span>
      </button>
      {#if addMenuOpen}
        <div class="add-menu">
          <p class="menu-title">AVAILABLE ROLES</p>
          {#each availableRoles as role (role)}
            {@const present = nodes.some((node) => node.data.role === role)}
            <button
              type="button"
              class="role-option"
              onclick={() => {
                addRole(role);
                addMenuOpen = false;
              }}
            >
              <span class="role-icon">{role.slice(0, 2)}</span>
              <span
                ><b>{role[0] + role.slice(1).toLowerCase()}</b><small
                  >{present ? 'Already on canvas' : 'Add to workflow'}</small
                ></span
              >
              <span class="ml-auto text-xs">{present ? '✓' : '+'}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
    <div class="hidden h-7 w-px bg-slate-700/70 sm:block"></div>
    <div>
      <p class="text-xs font-semibold text-heading">Workflow canvas</p>
      <p class="text-muted text-[10px]">Click an agent for actions · drag handles to connect</p>
    </div>
    <span class="text-muted ml-auto hidden text-[10px] md:inline"
      >{nodes.length} agents · {edges.length} routes</span
    >
    <Button size="sm" variant="primary" disabled={saving || !dirty} onclick={persist}>
      {saving ? 'Saving…' : dirty ? 'Save workflow' : 'Saved'}
    </Button>
  </div>
  {#if selectedNodeId}
    <div class="border-line flex items-center gap-3 border-b px-3 py-2 text-xs">
      <span class="text-muted">Incoming-message policy</span>
      <select class="border-line rounded border bg-input px-2 py-1" onchange={setActivationPolicy}>
        {#each ['any', 'all', 'required', 'manual', 'batch'] as policy (policy)}
          <option
            value={policy}
            selected={nodes.find((node) => node.id === selectedNodeId)?.data.activationPolicy ===
              policy}>{policy}</option
          >
        {/each}
      </select>
      <span class="text-muted">Controls when multiple upstream messages activate this agent.</span>
    </div>
  {:else if selectedEdgeId}
    <div class="border-line flex items-center gap-3 border-b px-3 py-2 text-xs">
      <span class="text-muted">Route when source reports</span>
      <select class="border-line rounded border bg-input px-2 py-1" onchange={setEdgeOutcome}>
        {#each ['success', 'failure', 'changes_requested', 'always'] as outcome (outcome)}
          <option
            value={outcome}
            selected={String(edges.find((edge) => edge.id === selectedEdgeId)?.data?.outcome) ===
              outcome}>{outcome.replaceAll('_', ' ')}</option
          >
        {/each}
      </select>
      <Button size="sm" variant="ghost" onclick={removeSelectedEdge}>Delete connection</Button>
    </div>
  {/if}
  <div class="relative h-[600px] bg-[#070b12]">
    <SvelteFlow
      bind:nodes
      bind:edges
      fitView
      minZoom={0.25}
      maxZoom={1.8}
      onconnect={connect}
      {nodeTypes}
      onnodeclick={({ node, event }) => selectNode(node as CanvasNode, event as MouseEvent)}
      onedgeclick={({ edge }) => {
        selectedEdgeId = edge.id;
        selectedNodeId = '';
      }}
      onnodedragstop={() => (dirty = true)}
      ondelete={() => (dirty = true)}
      defaultEdgeOptions={{ type: 'smoothstep', animated: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} patternColor="#263348" />
      <Controls />
      <MiniMap pannable zoomable />
    </SvelteFlow>
  </div>
</section>

{#if nodeMenu}
  {@const menuNode = nodes.find((node) => node.id === nodeMenu?.nodeId)}
  {#if menuNode}
    <div
      class="node-menu"
      style={`left:${Math.min(nodeMenu.x + 12, window.innerWidth - 220)}px;top:${Math.min(nodeMenu.y + 8, window.innerHeight - 150)}px`}
    >
      <div class="border-line border-b px-3 py-2">
        <p class="text-xs font-semibold text-heading">{menuNode.data.displayName}</p>
        <p class="text-muted text-[9px]">{menuNode.data.status.replaceAll('_', ' ')}</p>
      </div>
      <button type="button" onclick={editSelectedNode}>Edit configuration <span>→</span></button>
      <button
        type="button"
        class="danger"
        disabled={menuNode.data.system}
        onclick={() => removeNode(menuNode.id)}
      >
        {menuNode.data.system ? 'Required agent' : 'Delete from graph'}
        <span>{menuNode.data.system ? '⌁' : '×'}</span>
      </button>
    </div>
  {/if}
{/if}

<style>
  :global(.workflow-node) {
    min-width: 218px;
    border: 1px solid #35445d !important;
    border-radius: 12px !important;
    background: linear-gradient(145deg, #111a27, #0d1521) !important;
    color: #edf3ff !important;
    box-shadow: 0 12px 30px rgb(0 0 0 / 28%);
    transition:
      border-color 160ms ease,
      box-shadow 160ms ease,
      transform 160ms ease;
  }
  :global(.workflow-node:hover),
  :global(.workflow-node.selected) {
    border-color: #4f8cff !important;
    box-shadow:
      0 0 0 3px rgb(79 140 255 / 15%),
      0 16px 34px rgb(0 0 0 / 32%);
  }
  :global(.workflow-node.running) {
    border-color: #32d583 !important;
    animation: agent-running 1.4s ease-in-out infinite;
  }
  @keyframes agent-running {
    50% {
      box-shadow:
        0 0 0 7px rgb(50 213 131 / 12%),
        0 16px 34px rgb(0 0 0 / 32%);
    }
  }
  :global(.svelte-flow__edge-path) {
    stroke: #4f8cff;
    stroke-width: 2.2;
  }
  :global(.svelte-flow__handle) {
    width: 11px;
    height: 11px;
    border: 2px solid #101826;
    background: #6ea2ff;
  }
  .add-button {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    border: 1px solid rgb(96 165 250 / 45%);
    border-radius: 0.65rem;
    background: linear-gradient(120deg, rgb(37 99 235 / 25%), rgb(79 70 229 / 18%));
    padding: 0.55rem 0.8rem;
    color: #dbeafe;
    font-size: 0.75rem;
    font-weight: 700;
  }
  .add-button:hover {
    border-color: #60a5fa;
    background-color: rgb(37 99 235 / 28%);
  }
  .add-menu {
    position: absolute;
    z-index: 30;
    top: calc(100% + 0.55rem);
    left: 0;
    width: 250px;
    border: 1px solid #29364a;
    border-radius: 0.75rem;
    background: #0d1521;
    padding: 0.4rem;
    box-shadow: 0 20px 50px rgb(0 0 0 / 55%);
  }
  .menu-title {
    padding: 0.45rem 0.55rem;
    color: #64748b;
    font-size: 0.55rem;
    font-weight: 800;
    letter-spacing: 0.14em;
  }
  .role-option {
    display: flex;
    width: 100%;
    align-items: center;
    gap: 0.65rem;
    border-radius: 0.5rem;
    padding: 0.55rem;
    color: #cbd5e1;
    text-align: left;
  }
  .role-option:hover {
    background: #172235;
    color: white;
  }
  .role-option small {
    display: block;
    color: #64748b;
    font-size: 0.58rem;
    font-weight: 400;
  }
  .role-icon {
    display: grid;
    width: 1.8rem;
    height: 1.8rem;
    place-items: center;
    border-radius: 0.45rem;
    background: rgb(59 130 246 / 15%);
    color: #93c5fd;
    font-size: 0.55rem;
    font-weight: 800;
  }
  .node-menu {
    position: fixed;
    z-index: 80;
    width: 205px;
    overflow: hidden;
    border: 1px solid #334155;
    border-radius: 0.7rem;
    background: #0d1521;
    box-shadow: 0 18px 50px rgb(0 0 0 / 60%);
  }
  .node-menu button {
    display: flex;
    width: 100%;
    justify-content: space-between;
    padding: 0.65rem 0.75rem;
    color: #cbd5e1;
    font-size: 0.7rem;
    text-align: left;
  }
  .node-menu button:hover {
    background: #172235;
    color: white;
  }
  .node-menu button.danger {
    color: #fb7185;
  }
  .node-menu button:disabled {
    color: #64748b;
    cursor: not-allowed;
  }
</style>
