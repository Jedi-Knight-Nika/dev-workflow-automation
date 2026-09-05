<script lang="ts">
  import { untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import {
    Background,
    BackgroundVariant,
    Controls,
    MarkerType,
    SvelteFlow,
    addEdge,
    type Connection,
    type Edge,
    type Node
  } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';
  import type { AgentConfig, Integration, Repository, WorkflowGraph } from '$lib/types';
  import Button from '$lib/components/Button.svelte';
  import AgentNode from './AgentNode.svelte';
  import { discoverProviderModels, validateWorkflowNodeModel } from '$lib/services/agents';
  import type { ProviderCatalog } from '$lib/types';

  let {
    workflow,
    agents,
    integrations,
    repositories,
    selectedRole,
    onselect,
    onconsole,
    onsave
  }: {
    workflow: WorkflowGraph;
    agents: AgentConfig[];
    integrations: Integration[];
    repositories: Repository[];
    selectedRole: string;
    onselect: (role: string, nodeId: string) => void;
    onconsole: (role: string, nodeId: string) => void;
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
    onMenu?: (event: MouseEvent) => void;
    integrationIds: string[];
    repositoryIds: string[];
    provider: string;
    model: string;
    integrationNames: string[];
    repositoryCount: number;
    systemPrompt: string;
    modelValidationStatus: string;
    modelValidationMessage: string | null;
    modelValidatedAt: string | null;
  };
  type CanvasNode = Node<CanvasData>;
  function openNodeMenu(nodeId: string, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    const node = nodes.find((item) => item.id === nodeId);
    if (node) {
      selectedNodeId = node.id;
      selectedEdgeId = '';
      onselect(node.data.role, node.id);
    }
    nodeMenu = { x: event.clientX, y: event.clientY, nodeId };
    addMenuOpen = false;
  }

  function edgeClass(sourceRole?: string) {
    const running = agents.find((agent) => agent.role === sourceRole)?.status === 'RUNNING';
    return running ? 'route-processing' : 'route-neutral';
  }

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
        batchWindowSeconds: node.batch_window_seconds,
        integrationIds: node.integration_ids || [],
        repositoryIds: node.repository_ids || [],
        provider: node.provider || 'openai',
        model: node.model || '',
        integrationNames: [],
        repositoryCount: (node.repository_ids || []).length,
        systemPrompt: node.system_prompt || '',
        modelValidationStatus: node.model_validation_status || 'NOT_CONFIGURED',
        modelValidationMessage: node.model_validation_message,
        modelValidatedAt: node.model_validated_at,
        onMenu: (event: MouseEvent) => openNodeMenu(node.id, event)
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
      type: 'smoothstep',
      animated: true,
      markerEnd: MarkerType.ArrowClosed,
      data: { outcome: edge.outcome, required: edge.required },
      class: edgeClass(initialWorkflow.nodes.find((node) => node.id === edge.source_node_id)?.role)
    }))
  );
  let saving = $state(false);
  let dirty = $state(false);
  let selectedNodeId = $state('');
  let selectedEdgeId = $state('');
  let detailsNodeId = $state('');
  let nodeMenu = $state<{ x: number; y: number; nodeId: string } | null>(null);
  let addMenuOpen = $state(false);
  let modelCatalogs = $state<Record<string, ProviderCatalog>>({});
  let discoveringModels = $state(false);
  let validatingModel = $state(false);
  const manualModelNodes = new SvelteSet<string>();
  const nodeTypes = { agent: AgentNode };
  const availableRoles = ['INTAKE', 'THINKER', 'EXECUTOR', 'REVIEWER', 'TESTER'];

  $effect(() => {
    const statuses = new Map(agents.map((agent) => [agent.role, agent.status]));
    nodes = untrack(() => nodes).map((node) => {
      const status = statuses.get(node.data.role) || 'UNCONFIGURED';
      const integrationNames = node.data.integrationIds.flatMap((id) => {
        const integration = integrations.find((item) => item.id === id);
        return integration ? [integration.provider_name] : [];
      });
      return {
        ...node,
        data: {
          ...node.data,
          status,
          integrationNames,
          repositoryCount: node.data.repositoryIds.length
        },
        class: `workflow-node ${status === 'RUNNING' ? 'running' : ''} ${node.data.role === selectedRole ? 'selected' : ''}`
      };
    });
    const roles = new Map(untrack(() => nodes).map((node) => [node.id, node.data.role]));
    edges = untrack(() => edges).map((edge) => ({
      ...edge,
      class: edgeClass(roles.get(edge.source))
    }));
  });

  function selectNode(node: CanvasNode, event: MouseEvent) {
    selectedNodeId = node.id;
    selectedEdgeId = '';
    onselect(node.data.role, node.id);
    nodeMenu = null;
    if (event.detail >= 2) {
      detailsNodeId = node.id;
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
    const roleName = node.data.role[0] + node.data.role.slice(1).toLowerCase();
    const remaining = nodes.filter((item) => item.data.role === node.data.role);
    if (remaining.length === 1 && new RegExp(`^${roleName} \\d+$`).test(remaining[0].data.label)) {
      nodes = nodes.map((item) =>
        item.id === remaining[0].id
          ? { ...item, data: { ...item.data, label: roleName, displayName: roleName } }
          : item
      );
    }
    edges = edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
    selectedNodeId = '';
    nodeMenu = null;
    dirty = true;
  }

  function renameNode(nodeId: string, event: Event) {
    const value = (event.currentTarget as HTMLInputElement).value;
    nodes = nodes.map((node) =>
      node.id === nodeId
        ? { ...node, data: { ...node.data, label: value, displayName: value } }
        : node
    );
    dirty = true;
  }

  function toggleNodeAccess(
    nodeId: string,
    field: 'integrationIds' | 'repositoryIds',
    itemId: string,
    checked: boolean
  ) {
    nodes = nodes.map((node) => {
      if (node.id !== nodeId) return node;
      const current = node.data[field];
      const next = checked
        ? [...new Set([...current, itemId])]
        : current.filter((id) => id !== itemId);
      return { ...node, data: { ...node.data, [field]: next } };
    });
    dirty = true;
  }

  function updateNodeModel(
    nodeId: string,
    field: 'provider' | 'model' | 'systemPrompt',
    value: string
  ) {
    nodes = nodes.map((node) =>
      node.id === nodeId
        ? {
            ...node,
            data: {
              ...node.data,
              [field]: value,
              modelValidationStatus:
                field === 'systemPrompt' ? node.data.modelValidationStatus : 'UNVERIFIED',
              modelValidationMessage:
                field === 'systemPrompt'
                  ? node.data.modelValidationMessage
                  : 'Configuration changed; validate again',
              modelValidatedAt: field === 'systemPrompt' ? node.data.modelValidatedAt : null
            }
          }
        : node
    );
    dirty = true;
  }

  function changeNodeProvider(nodeId: string, event: Event) {
    const provider = (event.currentTarget as HTMLSelectElement).value;
    manualModelNodes.delete(nodeId);
    nodes = nodes.map((node) =>
      node.id === nodeId
        ? {
            ...node,
            data: {
              ...node.data,
              provider,
              model: '',
              modelValidationStatus: 'NOT_CONFIGURED',
              modelValidationMessage: 'Choose a model, then test the connection',
              modelValidatedAt: null
            }
          }
        : node
    );
    dirty = true;
  }

  async function discoverModels(provider: string) {
    discoveringModels = true;
    try {
      modelCatalogs[provider] = await discoverProviderModels(provider);
      modelCatalogs = { ...modelCatalogs };
    } finally {
      discoveringModels = false;
    }
  }

  async function validateModel(nodeId: string) {
    validatingModel = true;
    try {
      if (dirty) await persist();
      const result = await validateWorkflowNodeModel(nodeId);
      nodes = nodes.map((node) =>
        node.id === nodeId
          ? {
              ...node,
              data: {
                ...node.data,
                modelValidationStatus: result.status,
                modelValidationMessage: result.message,
                modelValidatedAt: result.validated_at
              }
            }
          : node
      );
    } finally {
      validatingModel = false;
    }
  }

  function chooseModel(nodeId: string, event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (value === '__manual__') {
      manualModelNodes.add(nodeId);
      updateNodeModel(nodeId, 'model', '');
      return;
    }
    updateNodeModel(nodeId, 'model', value);
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
        ? {
            ...edge,
            class: edgeClass(nodes.find((node) => node.id === edge.source)?.data.role),
            data: { ...edge.data, outcome: value }
          }
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
        data: { outcome: 'success', required: true },
        class: 'route-neutral'
      },
      edges
    );
    dirty = true;
  }

  function addRole(role: string) {
    if (role === 'ORCHESTRATOR' || role === 'DELIVERER') {
      const existing = nodes.find((node) => node.data.role === role);
      if (existing) onselect(role, existing.id);
      return;
    }
    const roleCount = nodes.filter((node) => node.data.role === role).length;
    const roleName = role[0] + role.slice(1).toLowerCase();
    if (roleCount === 1) {
      nodes = nodes.map((node) =>
        node.data.role === role && node.data.label === roleName
          ? {
              ...node,
              data: { ...node.data, label: `${roleName} 1`, displayName: `${roleName} 1` }
            }
          : node
      );
    }
    const usedNumbers = nodes
      .filter((node) => node.data.role === role)
      .map((node) => new RegExp(`^${roleName} (\\d+)$`).exec(node.data.label))
      .flatMap((match) => (match ? [Number(match[1])] : []));
    const nextNumber = Math.max(roleCount, ...usedNumbers) + 1;
    const nodeId = crypto.randomUUID();
    nodes = [
      ...nodes,
      {
        id: nodeId,
        position: { x: 420 + nodes.length * 45, y: 280 + (nodes.length % 3) * 110 },
        data: {
          label: roleCount ? `${roleName} ${nextNumber}` : roleName,
          displayName: roleCount ? `${roleName} ${nextNumber}` : roleName,
          role,
          status: agents.find((agent) => agent.role === role)?.status || 'UNCONFIGURED',
          system: false,
          activationPolicy: 'any',
          batchWindowSeconds: 0,
          integrationIds: [],
          repositoryIds: [],
          provider: agents.find((agent) => agent.role === role)?.provider || '',
          model: agents.find((agent) => agent.role === role)?.model || '',
          integrationNames: [],
          repositoryCount: 0,
          systemPrompt: '',
          modelValidationStatus: 'NOT_CONFIGURED',
          modelValidationMessage: null,
          modelValidatedAt: null,
          onMenu: (event: MouseEvent) => openNodeMenu(nodeId, event)
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
        batch_window_seconds: node.data.batchWindowSeconds,
        integration_ids: node.data.integrationIds,
        repository_ids: node.data.repositoryIds,
        provider: node.data.provider,
        model: node.data.model,
        system_prompt: node.data.systemPrompt,
        model_validation_status: node.data.modelValidationStatus,
        model_validation_message: node.data.modelValidationMessage,
        model_validated_at: node.data.modelValidatedAt
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
            {@const count = nodes.filter((node) => node.data.role === role).length}
            {@const protectedRole = role === 'ORCHESTRATOR' || role === 'DELIVERER'}
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
                  >{protectedRole && count
                    ? 'Already on canvas'
                    : count
                      ? `Add another · ${count} existing`
                      : 'Add to workflow'}</small
                ></span
              >
              <span class="ml-auto text-xs">{protectedRole && count ? '✓' : '+'}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
    <div class="hidden h-7 w-px bg-slate-700/70 sm:block"></div>
    <div>
      <p class="text-xs font-semibold text-heading">Workflow canvas</p>
      <p class="text-muted text-[10px]">
        Double-click for details · right-click or ••• for actions
      </p>
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
    {@const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId)}
    {@const sourceNode = nodes.find((node) => node.id === selectedEdge?.source)}
    {@const targetNode = nodes.find((node) => node.id === selectedEdge?.target)}
    <div class="border-line flex items-center gap-3 border-b px-3 py-2 text-xs">
      <span class="direction-summary">
        <b>{sourceNode?.data.displayName}</b><span>→</span><b>{targetNode?.data.displayName}</b>
      </span>
      <span class="text-muted">Activate target when source reports</span>
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
      onnodecontextmenu={({ node, event }) => openNodeMenu(node.id, event)}
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
    </SvelteFlow>
    <div class="canvas-legend">
      <span><i></i>Configured route</span><span><i class="processing"></i>Processing now</span>
    </div>
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

{#if detailsNodeId}
  {@const detailsNode = nodes.find((node) => node.id === detailsNodeId)}
  {@const detailsAgent = agents.find((agent) => agent.role === detailsNode?.data.role)}
  {#if detailsNode}
    <div class="modal-backdrop">
      <button
        class="modal-dismiss"
        type="button"
        aria-label="Close agent details"
        onclick={() => (detailsNodeId = '')}
      ></button>
      <div
        class="details-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${detailsNode.data.displayName} details`}
      >
        <header>
          <div class="details-avatar">{detailsNode.data.role.slice(0, 2)}</div>
          <div>
            <p class="text-brand text-[9px] font-bold tracking-[.14em]">{detailsNode.data.role}</p>
            <h2 class="text-lg font-semibold">Agent details</h2>
          </div>
          <button type="button" aria-label="Close details" onclick={() => (detailsNodeId = '')}
            >×</button
          >
        </header>
        <div class="p-5">
          <label class="nickname-label">
            Nickname <span>Shown on this workflow canvas</span>
            <input
              value={detailsNode.data.displayName}
              maxlength="80"
              oninput={(event) => renameNode(detailsNode.id, event)}
              onchange={() => void persist()}
              placeholder="Give this agent a nickname"
            />
          </label>
          <div class="details-grid">
            <div><span>STATUS</span><b>{detailsNode.data.status.replaceAll('_', ' ')}</b></div>
            <div><span>ROLE</span><b>{detailsNode.data.role}</b></div>
            <div><span>ACTIVATION</span><b>{detailsNode.data.activationPolicy}</b></div>
            <div><span>RUNS</span><b>{detailsAgent?.total_runs ?? 0}</b></div>
            <div><span>ACTIVE JOBS</span><b>{detailsAgent?.active_jobs ?? 0}</b></div>
            <div><span>MODEL</span><b>{detailsAgent?.model || 'Not configured'}</b></div>
          </div>
          <div class="access-section">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3>AI model</h3>
                <p>Choose a discovered model or enter an exact model ID manually.</p>
              </div>
              <span
                class="model-status"
                class:available={detailsNode.data.modelValidationStatus === 'AVAILABLE'}
                class:invalid={['MODEL_NOT_FOUND', 'UNAUTHORIZED', 'ERROR'].includes(
                  detailsNode.data.modelValidationStatus
                )}>{detailsNode.data.modelValidationStatus.replaceAll('_', ' ')}</span
              >
            </div>
            <div class="model-controls">
              <select
                value={detailsNode.data.provider}
                onchange={(event) => changeNodeProvider(detailsNode.id, event)}
              >
                <option value="openai">OpenAI</option><option value="anthropic"
                  >Anthropic / Claude</option
                ><option value="google">Google / Gemini</option>
              </select>
              {#if modelCatalogs[detailsNode.data.provider]?.models.length && !manualModelNodes.has(detailsNode.id)}
                <select
                  value={detailsNode.data.model}
                  onchange={(event) => chooseModel(detailsNode.id, event)}
                >
                  <option value="">Select a model</option>
                  {#each modelCatalogs[detailsNode.data.provider].models as model (model.id)}<option
                      value={model.id}>{model.display_name} · {model.id}</option
                    >{/each}
                  <option value="__manual__">Enter model ID manually…</option>
                </select>
              {:else}
                <input
                  value={detailsNode.data.model}
                  oninput={(event) =>
                    updateNodeModel(
                      detailsNode.id,
                      'model',
                      (event.currentTarget as HTMLInputElement).value
                    )}
                  placeholder="Exact model ID, e.g. claude-sonnet-4-5"
                />
              {/if}
            </div>
            <div class="mt-2 flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={discoveringModels}
                onclick={() => discoverModels(detailsNode.data.provider)}
                >{discoveringModels ? 'Loading…' : 'Load available models'}</Button
              >
              <Button
                size="sm"
                variant="success"
                disabled={validatingModel || !detailsNode.data.model.trim()}
                onclick={() => validateModel(detailsNode.id)}
                >{validatingModel ? 'Checking…' : 'Test model'}</Button
              >
              {#if detailsNode.data.modelValidationMessage}<span class="text-muted text-[10px]"
                  >{detailsNode.data.modelValidationMessage}</span
                >{/if}
            </div>
          </div>
          <div class="access-section">
            <div>
              <h3>System prompt</h3>
              <p>Node-specific instructions used by this exact agent.</p>
            </div>
            <textarea
              rows="5"
              value={detailsNode.data.systemPrompt}
              oninput={(event) =>
                updateNodeModel(
                  detailsNode.id,
                  'systemPrompt',
                  (event.currentTarget as HTMLTextAreaElement).value
                )}
              placeholder="Leave blank to use the role default."
            ></textarea>
          </div>
          {#if detailsNode.data.role === 'INTAKE' || detailsNode.data.role === 'DELIVERER'}
            <div class="access-section">
              <div>
                <h3>Connected integrations</h3>
                <p>Select services this node is allowed to use.</p>
              </div>
              <div class="access-list">
                {#each integrations as integration (integration.id)}
                  <label
                    ><input
                      type="checkbox"
                      checked={detailsNode.data.integrationIds.includes(integration.id)}
                      onchange={(event) =>
                        toggleNodeAccess(
                          detailsNode.id,
                          'integrationIds',
                          integration.id,
                          (event.currentTarget as HTMLInputElement).checked
                        )}
                    /><span
                      ><b>{integration.provider_name}</b><small
                        >{integration.provider_type} · {integration.status}</small
                      ></span
                    ></label
                  >
                {:else}<p>No integrations configured yet.</p>{/each}
              </div>
            </div>
          {/if}
          {#if !detailsNode.data.system}
            <div class="access-section">
              <div>
                <h3>Project and RAG access</h3>
                <p>Only selected indexed repositories are available to this agent node.</p>
              </div>
              <div class="access-list">
                {#each repositories.filter((repository) => repository.enabled) as repository (repository.id)}
                  <label
                    ><input
                      type="checkbox"
                      checked={detailsNode.data.repositoryIds.includes(repository.id)}
                      onchange={(event) =>
                        toggleNodeAccess(
                          detailsNode.id,
                          'repositoryIds',
                          repository.id,
                          (event.currentTarget as HTMLInputElement).checked
                        )}
                    /><span
                      ><b>{repository.owner}/{repository.name}</b><small
                        >{repository.index_status} · {repository.chunk_count} chunks</small
                      ></span
                    ></label
                  >
                {:else}<p>No enabled repositories available.</p>{/each}
              </div>
            </div>
          {/if}
          <div class="mt-5 flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onclick={() => onconsole(detailsNode.data.role, detailsNode.id)}>Live console</Button
            >
            <Button size="sm" variant="primary" disabled={saving || !dirty} onclick={persist}
              >{saving ? 'Saving…' : dirty ? 'Save node changes' : 'Saved'}</Button
            >
            <Button
              size="sm"
              variant="ghost"
              onclick={() => {
                onselect(detailsNode.data.role, detailsNode.id);
                detailsNodeId = '';
                document.getElementById('agent-inspector')?.scrollIntoView({ behavior: 'smooth' });
              }}>Full configuration</Button
            >
          </div>
        </div>
      </div>
    </div>
  {/if}
{/if}

<style>
  :global(.workflow-node) {
    min-width: 245px;
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
    stroke-width: 2.2;
  }
  :global(.route-neutral .svelte-flow__edge-path) {
    stroke: #64748b;
  }
  :global(.route-processing .svelte-flow__edge-path) {
    stroke: #38bdf8;
    stroke-width: 3;
    filter: drop-shadow(0 0 4px rgb(56 189 248 / 65%));
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
    border: 1px solid var(--color-brand);
    border-radius: 0.65rem;
    background: linear-gradient(120deg, var(--color-brand), var(--color-brand-2));
    padding: 0.55rem 0.8rem;
    color: white;
    font-size: 0.75rem;
    font-weight: 700;
    box-shadow: 0 5px 16px rgb(37 99 235 / 22%);
  }
  .add-button:hover {
    border-color: #60a5fa;
    filter: brightness(1.08);
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
  .direction-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid #334155;
    border-radius: 0.45rem;
    background: #0b1220;
    padding: 0.3rem 0.5rem;
    color: #cbd5e1;
    font-size: 0.62rem;
  }
  .direction-summary span {
    color: #60a5fa;
    font-size: 0.9rem;
  }
  .canvas-legend {
    position: absolute;
    right: 0.8rem;
    bottom: 0.65rem;
    z-index: 5;
    display: flex;
    gap: 0.8rem;
    border: 1px solid #263348;
    border-radius: 0.5rem;
    background: rgb(8 13 22 / 88%);
    padding: 0.4rem 0.55rem;
    color: #94a3b8;
    font-size: 0.55rem;
    backdrop-filter: blur(5px);
  }
  .canvas-legend span {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .canvas-legend i {
    width: 1rem;
    height: 2px;
    background: #64748b;
  }
  .canvas-legend i.processing {
    background: #38bdf8;
    box-shadow: 0 0 5px #38bdf8;
  }
  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 90;
    display: grid;
    place-items: center;
    background: rgb(2 6 12 / 78%);
    padding: 1rem;
    backdrop-filter: blur(5px);
  }
  .modal-dismiss {
    position: absolute;
    inset: 0;
    cursor: default;
  }
  .details-modal {
    position: relative;
    z-index: 1;
    width: min(560px, 100%);
    overflow: hidden;
    border: 1px solid #334155;
    border-radius: 1rem;
    background: #0d1521;
    box-shadow: 0 30px 90px rgb(0 0 0 / 65%);
  }
  .details-modal > header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    border-bottom: 1px solid #243044;
    padding: 1rem 1.2rem;
  }
  .details-modal > header > button {
    margin-left: auto;
    border-radius: 0.4rem;
    padding: 0.2rem 0.5rem;
    color: #94a3b8;
    font-size: 1.2rem;
  }
  .details-modal > header > button:hover {
    background: #1e293b;
    color: white;
  }
  .details-avatar {
    display: grid;
    width: 2.35rem;
    height: 2.35rem;
    place-items: center;
    border: 1px solid rgb(96 165 250 / 35%);
    border-radius: 0.65rem;
    background: rgb(37 99 235 / 18%);
    color: #bfdbfe;
    font-size: 0.65rem;
    font-weight: 800;
  }
  .nickname-label {
    display: block;
    color: #94a3b8;
    font-size: 0.65rem;
  }
  .nickname-label span {
    float: right;
    color: #64748b;
  }
  .nickname-label input {
    display: block;
    width: 100%;
    margin-top: 0.45rem;
    border: 1px solid #334155;
    border-radius: 0.55rem;
    background: #080f19;
    padding: 0.75rem;
    color: #e2e8f0;
    outline: none;
    font-size: 0.85rem;
  }
  .nickname-label input:focus {
    border-color: #60a5fa;
    box-shadow: 0 0 0 3px rgb(59 130 246 / 12%);
  }
  .details-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1px;
    margin-top: 1rem;
    overflow: hidden;
    border: 1px solid #243044;
    border-radius: 0.65rem;
    background: #243044;
  }
  .details-grid div {
    min-width: 0;
    background: #0a111c;
    padding: 0.75rem;
  }
  .details-grid span {
    display: block;
    color: #64748b;
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: 0.11em;
  }
  .details-grid b {
    display: block;
    overflow: hidden;
    margin-top: 0.25rem;
    color: #cbd5e1;
    font-size: 0.68rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .access-section {
    margin-top: 1rem;
    border-top: 1px solid #243044;
    padding-top: 1rem;
  }
  .access-section h3 {
    color: #e2e8f0;
    font-size: 0.75rem;
    font-weight: 650;
  }
  .access-section > div > p {
    margin-top: 0.15rem;
    color: #64748b;
    font-size: 0.6rem;
  }
  .access-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.4rem;
    margin-top: 0.65rem;
    max-height: 150px;
    overflow: auto;
  }
  .access-list label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid #243044;
    border-radius: 0.5rem;
    padding: 0.55rem;
    color: #cbd5e1;
    font-size: 0.65rem;
  }
  .access-list label:hover {
    border-color: #475569;
    background: #111c2b;
  }
  .access-list small {
    display: block;
    color: #64748b;
    font-size: 0.52rem;
  }
  .access-list > p {
    color: #64748b;
    font-size: 0.65rem;
  }
  .model-status {
    border: 1px solid #475569;
    border-radius: 999px;
    padding: 0.22rem 0.45rem;
    color: #94a3b8;
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: 0.08em;
  }
  .model-status.available {
    border-color: rgb(52 211 153 / 35%);
    color: #6ee7b7;
  }
  .model-status.invalid {
    border-color: rgb(251 113 133 / 35%);
    color: #fda4af;
  }
  .model-controls {
    display: grid;
    grid-template-columns: 0.7fr 1.3fr;
    gap: 0.5rem;
    margin-top: 0.65rem;
  }
  .model-controls select,
  .model-controls input,
  .access-section textarea {
    width: 100%;
    border: 1px solid #334155;
    border-radius: 0.5rem;
    background: #080f19;
    padding: 0.62rem 0.7rem;
    color: #e2e8f0;
    outline: none;
    font-size: 0.68rem;
  }
  .model-controls select:focus,
  .model-controls input:focus,
  .access-section textarea:focus {
    border-color: #60a5fa;
  }
  .access-section textarea {
    margin-top: 0.65rem;
    resize: vertical;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    line-height: 1.5;
  }
  @media (min-width: 560px) {
    .details-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }
</style>
