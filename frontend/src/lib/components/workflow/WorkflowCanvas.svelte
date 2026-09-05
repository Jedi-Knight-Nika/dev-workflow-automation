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
  import type { WorkflowGraph } from '$lib/types';
  import Button from '$lib/components/Button.svelte';

  let {
    workflow,
    selectedRole,
    onselect,
    onsave
  }: {
    workflow: WorkflowGraph;
    selectedRole: string;
    onselect: (role: string) => void;
    onsave: (graph: WorkflowGraph) => Promise<void>;
  } = $props();

  type CanvasData = {
    label: string;
    role: string;
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
        role: node.role,
        system: node.role === 'ORCHESTRATOR' || node.role === 'DELIVERER',
        activationPolicy: node.activation_policy,
        batchWindowSeconds: node.batch_window_seconds
      },
      deletable: node.role !== 'ORCHESTRATOR' && node.role !== 'DELIVERER',
      class: node.role === selectedRole ? 'workflow-node selected' : 'workflow-node'
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

  function selectNode(node: CanvasNode) {
    selectedNodeId = node.id;
    selectedEdgeId = '';
    onselect(node.data.role);
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
      onselect(role);
      return;
    }
    nodes = [
      ...nodes,
      {
        id: crypto.randomUUID(),
        position: { x: 420 + nodes.length * 45, y: 280 + (nodes.length % 3) * 110 },
        data: {
          label: role[0] + role.slice(1).toLowerCase(),
          role,
          system: false,
          activationPolicy: 'any',
          batchWindowSeconds: 0
        },
        deletable: true,
        class: 'workflow-node'
      }
    ];
    onselect(role);
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
  <div class="border-line flex flex-wrap items-center gap-2 border-b p-3">
    <span class="text-brand mr-2 font-mono text-[10px]">ADD AGENT</span>
    {#each ['INTAKE', 'THINKER', 'EXECUTOR', 'REVIEWER', 'TESTER'] as role (role)}
      <button
        type="button"
        class="border-brand/40 bg-brand/10 hover:bg-brand/20 rounded-md border px-3 py-1.5 text-xs transition"
        onclick={() => addRole(role)}>+ {role[0] + role.slice(1).toLowerCase()}</button
      >
    {/each}
    <span class="text-muted ml-auto text-[10px]">Drag nodes · connect handles · Delete removes</span
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
  <div class="h-[560px] bg-[#080d16]">
    <SvelteFlow
      bind:nodes
      bind:edges
      fitView
      minZoom={0.25}
      maxZoom={1.8}
      onconnect={connect}
      onnodeclick={({ node }) => selectNode(node as CanvasNode)}
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

<style>
  :global(.workflow-node) {
    min-width: 170px;
    border: 1px solid #35445d !important;
    border-radius: 12px !important;
    background: #111a28 !important;
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
</style>
