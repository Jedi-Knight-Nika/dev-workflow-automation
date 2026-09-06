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
  import Spinner from '$lib/components/Spinner.svelte';
  import AgentNode from './AgentNode.svelte';
  import { discoverProviderModels, validateWorkflowNodeModel } from '$lib/services/agents';
  import type { ProviderCatalog } from '$lib/types';
  import type { LinearMember, LinearWorkflowState } from '$lib/types';
  import { listLinearMembers, listLinearWorkflowStates } from '$lib/services/integrations';
  import { t } from '$lib/i18n/index.svelte';
  import { getTheme } from '$lib/theme.svelte';

  let {
    workflow,
    agents,
    integrations,
    repositories,
    teamId,
    selectedRole,
    onSelect,
    onConsole,
    onSave
  }: {
    workflow: WorkflowGraph;
    agents: AgentConfig[];
    integrations: Integration[];
    repositories: Repository[];
    teamId?: string;
    selectedRole: string;
    onSelect: (role: string, nodeId: string) => void;
    onConsole: (role: string, nodeId: string) => void;
    onSave: (graph: WorkflowGraph) => Promise<void>;
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
    integrationMode: string;
    pollIntervalSeconds: number;
    filterAssigneeId: string;
    filterStateIds: string[];
    integrationSyncStatus: string;
    integrationSyncError: string | null;
    integrationLastSyncedAt: string | null;
    enabled: boolean;
    reasoningEffort: string;
    maxOutputTokens: number | null;
    temperature: number | null;
    timeoutMinutes: number;
    maxRetries: number;
    maxReviewCycles: number;
    contextDepth: string;
    ragRetrievalDepth: string;
    fallbackProvider: string;
    fallbackModel: string;
    agentId: string | null;
  };
  type CanvasNode = Node<CanvasData>;
  function openNodeMenu(nodeId: string, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    const node = nodes.find((item) => item.id === nodeId);
    if (node) {
      selectedNodeId = node.id;
      selectedEdgeId = '';
      onSelect(node.data.role, node.id);
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
        integrationMode: node.integration_mode || 'webhook',
        pollIntervalSeconds: node.poll_interval_seconds || 300,
        filterAssigneeId: node.filter_assignee_id || '',
        filterStateIds: node.filter_state_ids || [],
        integrationSyncStatus: node.integration_sync_status || 'IDLE',
        integrationSyncError: node.integration_sync_error,
        integrationLastSyncedAt: node.integration_last_synced_at,
        enabled: node.enabled,
        reasoningEffort: node.reasoning_effort || 'default',
        maxOutputTokens: node.max_output_tokens,
        temperature: node.temperature,
        timeoutMinutes: node.timeout_minutes || 60,
        maxRetries: node.max_retries ?? 2,
        maxReviewCycles: node.max_review_cycles ?? 3,
        contextDepth: node.context_depth || 'normal',
        ragRetrievalDepth: node.rag_retrieval_depth || 'normal',
        fallbackProvider: node.fallback_provider || '',
        fallbackModel: node.fallback_model || '',
        agentId: node.agent_id,
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
      data: { ...edge },
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
  let linearMembers = $state<LinearMember[]>([]);
  let linearStates = $state<LinearWorkflowState[]>([]);
  let loadingLinearFilters = $state(false);
  const nodeTypes = { agent: AgentNode };
  const availableRoles = ['INTAKE', 'THINKER', 'EXECUTOR', 'REVIEWER', 'TESTER'];
  const reasoningLevels = ['default', 'low', 'medium', 'high', 'max'];
  const depthLevels = ['low', 'normal', 'deep'];
  const timeoutLevels = [30, 60, 120, 240];
  const titleCase = (value: string) => value[0].toUpperCase() + value.slice(1);
  const percent = (value: number, min: number, max: number) => ((value - min) / (max - min)) * 100;

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
        class: `workflow-node ${status === 'RUNNING' ? 'running' : ''} ${!node.data.enabled ? 'disabled' : ''} ${node.data.role === selectedRole ? 'selected' : ''}`
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
    onSelect(node.data.role, node.id);
    nodeMenu = null;
    if (event.detail >= 2) {
      detailsNodeId = node.id;
    }
    addMenuOpen = false;
  }

  function editSelectedNode() {
    const node = nodes.find((item) => item.id === nodeMenu?.nodeId);
    if (node) onSelect(node.data.role, node.id);
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

  function updateExecutionSetting(nodeId: string, values: Partial<CanvasData>) {
    nodes = nodes.map((node) =>
      node.id === nodeId ? { ...node, data: { ...node.data, ...values } } : node
    );
    dirty = true;
  }

  function supportsTemperature(node: CanvasNode) {
    if (node.data.provider !== 'openai') return true;
    return !/^(o[134]|gpt-5)/i.test(node.data.model);
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

  async function loadLinearFilters() {
    loadingLinearFilters = true;
    try {
      [linearMembers, linearStates] = await Promise.all([
        listLinearMembers(),
        listLinearWorkflowStates()
      ]);
    } finally {
      loadingLinearFilters = false;
    }
  }

  function updateIntegrationSchedule(
    nodeId: string,
    values: Partial<
      Pick<CanvasData, 'integrationMode' | 'pollIntervalSeconds' | 'filterAssigneeId'>
    >
  ) {
    nodes = nodes.map((node) =>
      node.id === nodeId ? { ...node, data: { ...node.data, ...values } } : node
    );
    dirty = true;
  }

  function toggleLinearState(nodeId: string, stateId: string, checked: boolean) {
    nodes = nodes.map((node) =>
      node.id === nodeId
        ? {
            ...node,
            data: {
              ...node.data,
              filterStateIds: checked
                ? node.data.filterStateIds.includes(stateId)
                  ? node.data.filterStateIds
                  : [...node.data.filterStateIds, stateId]
                : node.data.filterStateIds.filter((id) => id !== stateId)
            }
          }
        : node
    );
    dirty = true;
  }

  async function validateModel(nodeId: string) {
    validatingModel = true;
    try {
      if (dirty) await persist();
      const result = await validateWorkflowNodeModel(nodeId, teamId);
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
        data: {
          outcome: 'success',
          required: true,
          job_type: null,
          internal_task_state: null,
          external_status_key: null,
          priority_override: null,
          configuration: {}
        },
        class: 'route-neutral'
      },
      edges
    );
    dirty = true;
  }

  function addRole(role: string) {
    if (role === 'ORCHESTRATOR' || role === 'DELIVERER') {
      const existing = nodes.find((node) => node.data.role === role);
      if (existing) onSelect(role, existing.id);
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
          integrationMode: 'webhook',
          pollIntervalSeconds: 300,
          filterAssigneeId: '',
          filterStateIds: [],
          integrationSyncStatus: 'IDLE',
          integrationSyncError: null,
          integrationLastSyncedAt: null,
          enabled: true,
          reasoningEffort: 'default',
          maxOutputTokens: null,
          temperature: null,
          timeoutMinutes: 60,
          maxRetries: 2,
          maxReviewCycles: 3,
          contextDepth: 'normal',
          ragRetrievalDepth: 'normal',
          fallbackProvider: '',
          fallbackModel: '',
          agentId: null,
          onMenu: (event: MouseEvent) => openNodeMenu(nodeId, event)
        },
        deletable: true,
        class: 'workflow-node',
        type: 'agent'
      }
    ];
    onSelect(role, nodes[nodes.length - 1].id);
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
        enabled: node.data.enabled,
        activation_policy: node.data.activationPolicy,
        batch_window_seconds: node.data.batchWindowSeconds,
        integration_ids: node.data.integrationIds,
        repository_ids: node.data.repositoryIds,
        provider: node.data.provider,
        model: node.data.model,
        system_prompt: node.data.systemPrompt,
        model_validation_status: node.data.modelValidationStatus,
        model_validation_message: node.data.modelValidationMessage,
        model_validated_at: node.data.modelValidatedAt,
        integration_mode: node.data.integrationMode,
        poll_interval_seconds: node.data.pollIntervalSeconds,
        filter_assignee_id: node.data.filterAssigneeId,
        filter_state_ids: node.data.filterStateIds,
        integration_sync_status: node.data.integrationSyncStatus,
        integration_sync_error: node.data.integrationSyncError,
        integration_last_synced_at: node.data.integrationLastSyncedAt,
        reasoning_effort: node.data
          .reasoningEffort as WorkflowGraph['nodes'][number]['reasoning_effort'],
        max_output_tokens: node.data.maxOutputTokens,
        temperature: node.data.temperature,
        timeout_minutes: node.data.timeoutMinutes,
        max_retries: node.data.maxRetries,
        max_review_cycles: node.data.maxReviewCycles,
        context_depth: node.data.contextDepth as WorkflowGraph['nodes'][number]['context_depth'],
        rag_retrieval_depth: node.data
          .ragRetrievalDepth as WorkflowGraph['nodes'][number]['rag_retrieval_depth'],
        fallback_provider: node.data.fallbackProvider || null,
        fallback_model: node.data.fallbackModel || null,
        agent_id: node.data.agentId,
        node_type: 'AGENT',
        system_node_type: null
      })),
      edges: edges
        .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
        .map((edge) => ({
          id: edge.id,
          source_node_id: edge.source,
          target_node_id: edge.target,
          outcome: String(edge.data?.outcome || 'success'),
          required: edge.data?.required !== false,
          job_type: edge.data?.job_type ? String(edge.data.job_type) : null,
          internal_task_state: edge.data?.internal_task_state
            ? String(edge.data.internal_task_state)
            : null,
          external_status_key: edge.data?.external_status_key
            ? String(edge.data.external_status_key)
            : null,
          priority_override:
            typeof edge.data?.priority_override === 'number' ? edge.data.priority_override : null,
          configuration:
            edge.data?.configuration && typeof edge.data.configuration === 'object'
              ? (edge.data.configuration as Record<string, unknown>)
              : {}
        }))
    };
    try {
      await onSave(graph);
      dirty = false;
    } catch {
      // onSave already records the error for display; nothing further to do here.
    } finally {
      saving = false;
    }
  }
</script>

<section class="border-line bg-panel mb-6 overflow-hidden rounded-xl border">
  <div class="border-line flex min-h-16 flex-wrap items-center gap-3 border-b px-4 py-3">
    <div class="relative">
      <button class="add-button" type="button" onclick={() => (addMenuOpen = !addMenuOpen)}>
        <span class="text-lg leading-none">+</span>
        {t('workflow.addAgent')}
        <span class="text-[9px] opacity-60">▼</span>
      </button>
      {#if addMenuOpen}
        <div class="add-menu">
          <p class="menu-title">{t('workflow.availableRoles')}</p>
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
                    ? t('workflow.alreadyOnCanvas')
                    : count
                      ? t('workflow.addAnotherExisting', { count })
                      : t('workflow.addToWorkflow')}</small
                ></span
              >
              <span class="ml-auto text-xs">{protectedRole && count ? '✓' : '+'}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
    <div class="hidden h-7 w-px bg-[var(--color-line)] sm:block"></div>
    <div>
      <p class="text-xs font-semibold text-heading">{t('workflow.canvasHeading')}</p>
      <p class="text-muted text-[10px]">
        {t('workflow.canvasHint')}
      </p>
    </div>
    <span class="text-muted ml-auto hidden text-[10px] md:inline"
      >{t('workflow.canvasStats', { nodes: nodes.length, edges: edges.length })}</span
    >
    <Button size="sm" variant="primary" disabled={saving || !dirty} onclick={persist}>
      <span class="flex items-center gap-1.5">
        {#if saving}<Spinner class="size-3" />{/if}
        {saving ? t('workflow.saving') : dirty ? t('workflow.saveWorkflow') : t('workflow.saved')}
      </span>
    </Button>
  </div>
  {#if selectedNodeId}
    <div class="border-line flex items-center gap-3 border-b px-3 py-2 text-xs">
      <span class="text-muted">{t('workflow.incomingMessagePolicy')}</span>
      <select class="border-line rounded border bg-input px-2 py-1" onchange={setActivationPolicy}>
        {#each ['any', 'all', 'required', 'manual', 'batch'] as policy (policy)}
          <option
            value={policy}
            selected={nodes.find((node) => node.id === selectedNodeId)?.data.activationPolicy ===
              policy}>{policy}</option
          >
        {/each}
      </select>
      <span class="text-muted">{t('workflow.activationPolicyHint')}</span>
    </div>
  {:else if selectedEdgeId}
    {@const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId)}
    {@const sourceNode = nodes.find((node) => node.id === selectedEdge?.source)}
    {@const targetNode = nodes.find((node) => node.id === selectedEdge?.target)}
    <div class="border-line flex items-center gap-3 border-b px-3 py-2 text-xs">
      <span class="direction-summary">
        <b>{sourceNode?.data.displayName}</b><span>→</span><b>{targetNode?.data.displayName}</b>
      </span>
      <span class="text-muted">{t('workflow.activateOnOutcome')}</span>
      <select class="border-line rounded border bg-input px-2 py-1" onchange={setEdgeOutcome}>
        {#each ['success', 'failure', 'changes_requested', 'always'] as outcome (outcome)}
          <option
            value={outcome}
            selected={String(edges.find((edge) => edge.id === selectedEdgeId)?.data?.outcome) ===
              outcome}>{outcome.replaceAll('_', ' ')}</option
          >
        {/each}
      </select>
      <Button size="sm" variant="ghost" onclick={removeSelectedEdge}
        >{t('workflow.deleteConnection')}</Button
      >
    </div>
  {/if}
  <div class="relative h-[600px] bg-surface">
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
      colorMode={getTheme()}
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={22}
        size={1.2}
        patternColor="var(--color-line)"
      />
      <Controls />
    </SvelteFlow>
    <div class="canvas-legend">
      <span><i></i>{t('workflow.configuredRoute')}</span><span
        ><i class="processing"></i>{t('workflow.processingNow')}</span
      >
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
      <button type="button" onclick={editSelectedNode}
        >{t('workflow.editConfiguration')} <span>→</span></button
      >
      <button
        type="button"
        class="danger"
        disabled={menuNode.data.system}
        onclick={() => removeNode(menuNode.id)}
      >
        {menuNode.data.system ? t('workflow.requiredAgent') : t('workflow.deleteFromGraph')}
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
        aria-label={t('workflow.closeDetails')}
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
            <h2 class="text-lg font-semibold">{t('workflow.agentDetails')}</h2>
          </div>
          <button
            type="button"
            aria-label={t('workflow.closeDetails')}
            onclick={() => (detailsNodeId = '')}>×</button
          >
        </header>
        <div class="p-5">
          <label class="nickname-label">
            {t('workflow.nickname')} <span>{t('workflow.nicknameHint')}</span>
            <input
              value={detailsNode.data.displayName}
              maxlength="80"
              oninput={(event) => renameNode(detailsNode.id, event)}
              onchange={() => void persist()}
              placeholder={t('workflow.nicknamePlaceholder')}
            />
          </label>
          <div class="details-grid">
            <div>
              <span>{t('workflow.statusLabel')}</span><b
                >{detailsNode.data.status.replaceAll('_', ' ')}</b
              >
            </div>
            <div><span>{t('workflow.roleLabel')}</span><b>{detailsNode.data.role}</b></div>
            <div>
              <span>{t('workflow.activationLabel')}</span><b>{detailsNode.data.activationPolicy}</b>
            </div>
            <div><span>{t('workflow.runsLabel')}</span><b>{detailsAgent?.total_runs ?? 0}</b></div>
            <div>
              <span>{t('workflow.activeJobsLabel')}</span><b>{detailsAgent?.active_jobs ?? 0}</b>
            </div>
            <div>
              <span>{t('workflow.modelLabel')}</span><b
                >{detailsAgent?.model || t('workflow.notConfigured')}</b
              >
            </div>
          </div>
          <div class="access-section">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3>{t('workflow.aiModel')}</h3>
                <p>{t('workflow.aiModelHint')}</p>
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
                  <option value="">{t('workflow.selectModel')}</option>
                  {#each modelCatalogs[detailsNode.data.provider].models as model (model.id)}<option
                      value={model.id}>{model.display_name} · {model.id}</option
                    >{/each}
                  <option value="__manual__">{t('workflow.enterModelIdManually')}</option>
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
                  placeholder={t('workflow.modelIdPlaceholder')}
                />
              {/if}
            </div>
            <div class="mt-2 flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={discoveringModels}
                onclick={() => discoverModels(detailsNode.data.provider)}
              >
                <span class="flex items-center gap-1.5">
                  {#if discoveringModels}<Spinner class="size-3" />{/if}
                  {discoveringModels
                    ? t('workflow.loadingEllipsis')
                    : t('workflow.loadAvailableModels')}
                </span>
              </Button>
              <Button
                size="sm"
                variant="success"
                disabled={validatingModel || !detailsNode.data.model.trim()}
                onclick={() => validateModel(detailsNode.id)}
              >
                <span class="flex items-center gap-1.5">
                  {#if validatingModel}<Spinner class="size-3" />{/if}
                  {validatingModel ? t('workflow.checkingEllipsis') : t('workflow.testModel')}
                </span>
              </Button>
              {#if detailsNode.data.modelValidationMessage}<span class="text-muted text-[10px]"
                  >{detailsNode.data.modelValidationMessage}</span
                >{/if}
            </div>
          </div>
          <div class="access-section">
            <div>
              <h3>{t('workflow.nodeSystemPrompt')}</h3>
              <p>{t('workflow.nodeSystemPromptHint')}</p>
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
              placeholder={t('workflow.systemPromptPlaceholder')}
            ></textarea>
          </div>
          <details class="access-section advanced-settings" open>
            <summary>Advanced execution settings</summary>
            <p>Applied by the worker each time this agent runs.</p>
            <label class="enabled-toggle">
              <input
                type="checkbox"
                checked={detailsNode.data.enabled}
                onchange={(event) =>
                  updateExecutionSetting(detailsNode.id, { enabled: event.currentTarget.checked })}
              />
              <span
                ><b>Enabled</b><small
                  >{detailsNode.data.enabled
                    ? 'Agent participates in this workflow'
                    : 'Agent is disabled'}</small
                ></span
              >
            </label>
            <div class="advanced-grid">
              <label class="range-field"
                ><span>Reasoning effort <b>{titleCase(detailsNode.data.reasoningEffort)}</b></span
                ><input
                  class="range"
                  type="range"
                  min="0"
                  max="4"
                  step="1"
                  value={reasoningLevels.indexOf(detailsNode.data.reasoningEffort)}
                  style={`--range:${percent(reasoningLevels.indexOf(detailsNode.data.reasoningEffort), 0, 4)}%`}
                  oninput={(event) =>
                    updateExecutionSetting(detailsNode.id, {
                      reasoningEffort: reasoningLevels[Number(event.currentTarget.value)]
                    })}
                /><small>Default · Low · Medium · High · Max</small></label
              >
              <label class="range-field"
                ><span
                  >Max output tokens <b
                    >{detailsNode.data.maxOutputTokens?.toLocaleString() || 'Provider default'}</b
                  ></span
                >
                <div class="range-switch">
                  <input
                    type="checkbox"
                    checked={detailsNode.data.maxOutputTokens !== null}
                    onchange={(event) =>
                      updateExecutionSetting(detailsNode.id, {
                        maxOutputTokens: event.currentTarget.checked ? 4096 : null
                      })}
                  /><small>Custom limit</small>
                </div>
                {#if detailsNode.data.maxOutputTokens !== null}<input
                    class="range"
                    type="range"
                    min="256"
                    max="32768"
                    step="256"
                    value={detailsNode.data.maxOutputTokens}
                    style={`--range:${percent(detailsNode.data.maxOutputTokens, 256, 32768)}%`}
                    oninput={(event) =>
                      updateExecutionSetting(detailsNode.id, {
                        maxOutputTokens: Number(event.currentTarget.value)
                      })}
                  />{/if}</label
              >
              {#if supportsTemperature(detailsNode)}<label class="range-field"
                  ><span
                    >Temperature <b
                      >{detailsNode.data.temperature === null
                        ? 'Provider default'
                        : detailsNode.data.temperature.toFixed(1)}</b
                    ></span
                  >
                  <div class="range-switch">
                    <input
                      type="checkbox"
                      checked={detailsNode.data.temperature !== null}
                      onchange={(event) =>
                        updateExecutionSetting(detailsNode.id, {
                          temperature: event.currentTarget.checked ? 0.7 : null
                        })}
                    /><small>Custom value</small>
                  </div>
                  {#if detailsNode.data.temperature !== null}<input
                      class="range"
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={detailsNode.data.temperature}
                      style={`--range:${percent(detailsNode.data.temperature, 0, 2)}%`}
                      oninput={(event) =>
                        updateExecutionSetting(detailsNode.id, {
                          temperature: Number(event.currentTarget.value)
                        })}
                    /><small>Precise ↔ Creative</small>{/if}</label
                >{/if}
              <label class="range-field"
                ><span>Timeout <b>{detailsNode.data.timeoutMinutes} min</b></span><input
                  class="range"
                  type="range"
                  min="0"
                  max="3"
                  step="1"
                  value={Math.max(0, timeoutLevels.indexOf(detailsNode.data.timeoutMinutes))}
                  style={`--range:${percent(Math.max(0, timeoutLevels.indexOf(detailsNode.data.timeoutMinutes)), 0, 3)}%`}
                  oninput={(event) =>
                    updateExecutionSetting(detailsNode.id, {
                      timeoutMinutes: timeoutLevels[Number(event.currentTarget.value)]
                    })}
                /><small>30m · 60m · 120m · 240m</small></label
              >
              <label class="range-field"
                ><span>Max retries <b>{detailsNode.data.maxRetries}</b></span><input
                  class="range"
                  type="range"
                  min="0"
                  max="10"
                  step="1"
                  value={detailsNode.data.maxRetries}
                  style={`--range:${percent(detailsNode.data.maxRetries, 0, 10)}%`}
                  oninput={(event) =>
                    updateExecutionSetting(detailsNode.id, {
                      maxRetries: Number(event.currentTarget.value)
                    })}
                /><small>0 retries ↔ 10 retries</small></label
              >
              {#if ['EXECUTOR', 'REVIEWER', 'TESTER'].includes(detailsNode.data.role)}<label
                  class="range-field"
                  ><span>Max review/fix cycles <b>{detailsNode.data.maxReviewCycles}</b></span
                  ><input
                    class="range"
                    type="range"
                    min="0"
                    max="20"
                    step="1"
                    value={detailsNode.data.maxReviewCycles}
                    style={`--range:${percent(detailsNode.data.maxReviewCycles, 0, 20)}%`}
                    oninput={(event) =>
                      updateExecutionSetting(detailsNode.id, {
                        maxReviewCycles: Number(event.currentTarget.value)
                      })}
                  /><small>Stop early ↔ More iterations</small></label
                >{/if}
              <label class="range-field"
                ><span>Context depth <b>{titleCase(detailsNode.data.contextDepth)}</b></span><input
                  class="range"
                  type="range"
                  min="0"
                  max="2"
                  step="1"
                  value={depthLevels.indexOf(detailsNode.data.contextDepth)}
                  style={`--range:${percent(depthLevels.indexOf(detailsNode.data.contextDepth), 0, 2)}%`}
                  oninput={(event) =>
                    updateExecutionSetting(detailsNode.id, {
                      contextDepth: depthLevels[Number(event.currentTarget.value)]
                    })}
                /><small>Low · Normal · Deep</small></label
              >
              <label class="range-field"
                ><span
                  >RAG retrieval depth <b>{titleCase(detailsNode.data.ragRetrievalDepth)}</b></span
                ><input
                  class="range"
                  type="range"
                  min="0"
                  max="2"
                  step="1"
                  value={depthLevels.indexOf(detailsNode.data.ragRetrievalDepth)}
                  style={`--range:${percent(depthLevels.indexOf(detailsNode.data.ragRetrievalDepth), 0, 2)}%`}
                  oninput={(event) =>
                    updateExecutionSetting(detailsNode.id, {
                      ragRetrievalDepth: depthLevels[Number(event.currentTarget.value)]
                    })}
                /><small>Low · Normal · Deep</small></label
              >
              <label
                ><span>Fallback provider <small>optional</small></span><select
                  value={detailsNode.data.fallbackProvider}
                  onchange={(event) =>
                    updateExecutionSetting(detailsNode.id, {
                      fallbackProvider: event.currentTarget.value,
                      fallbackModel: ''
                    })}
                  ><option value="">None</option><option value="openai">OpenAI</option><option
                    value="anthropic">Anthropic</option
                  ><option value="google">Google</option></select
                ></label
              >
              {#if detailsNode.data.fallbackProvider}<label
                  ><span>Fallback model</span><input
                    value={detailsNode.data.fallbackModel}
                    placeholder="Model ID"
                    oninput={(event) =>
                      updateExecutionSetting(detailsNode.id, {
                        fallbackModel: event.currentTarget.value
                      })}
                  /></label
                >{/if}
            </div>
          </details>
          {#if detailsNode.data.role === 'INTAKE' || detailsNode.data.role === 'DELIVERER'}
            <div class="access-section">
              <div>
                <h3>{t('workflow.connectedIntegrations')}</h3>
                <p>{t('workflow.connectedIntegrationsHint')}</p>
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
                {:else}<p>{t('workflow.noIntegrationsConfigured')}</p>{/each}
              </div>
              {#if detailsNode.data.role === 'INTAKE'}
                <div class="integration-schedule">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3>{t('workflow.linearTaskIntake')}</h3>
                      <p>
                        {t('workflow.linearTaskIntakeHint')}
                      </p>
                    </div>
                    <span class="model-status">{detailsNode.data.integrationSyncStatus}</span>
                  </div>
                  <label>
                    <span>{t('workflow.triggerMode')}</span>
                    <select
                      value={detailsNode.data.integrationMode}
                      onchange={(event) =>
                        updateIntegrationSchedule(detailsNode.id, {
                          integrationMode: (event.currentTarget as HTMLSelectElement).value
                        })}
                    >
                      <option value="webhook">{t('workflow.triggerWebhookOnly')}</option>
                      <option value="hybrid">{t('workflow.triggerHybrid')}</option>
                      <option value="poll">{t('workflow.triggerPollOnly')}</option>
                      <option value="manual">{t('workflow.triggerManualOnly')}</option>
                    </select>
                  </label>
                  {#if ['hybrid', 'poll'].includes(detailsNode.data.integrationMode)}
                    <label>
                      <span>{t('workflow.pollEvery')}</span>
                      <select
                        value={detailsNode.data.pollIntervalSeconds}
                        onchange={(event) =>
                          updateIntegrationSchedule(detailsNode.id, {
                            pollIntervalSeconds: Number(
                              (event.currentTarget as HTMLSelectElement).value
                            )
                          })}
                      >
                        <option value="60">{t('workflow.interval1m')}</option><option value="300"
                          >{t('workflow.interval5m')}</option
                        ><option value="900">{t('workflow.interval15m')}</option><option
                          value="3600">{t('workflow.interval1h')}</option
                        >
                      </select>
                    </label>
                    <Button size="sm" disabled={loadingLinearFilters} onclick={loadLinearFilters}>
                      <span class="flex items-center gap-1.5">
                        {#if loadingLinearFilters}<Spinner class="size-3" />{/if}
                        {loadingLinearFilters
                          ? t('workflow.loadingEllipsis')
                          : t('workflow.loadLinearUsersStates')}
                      </span>
                    </Button>
                    <label>
                      <span>{t('workflow.assignedLinearUser')}</span>
                      <select
                        value={detailsNode.data.filterAssigneeId}
                        onchange={(event) =>
                          updateIntegrationSchedule(detailsNode.id, {
                            filterAssigneeId: (event.currentTarget as HTMLSelectElement).value
                          })}
                      >
                        <option value="">{t('workflow.selectAUser')}</option>
                        {#each linearMembers.filter((member) => member.active) as member (member.id)}
                          <option value={member.id}>{member.name} · {member.email}</option>
                        {/each}
                      </select>
                    </label>
                    <div>
                      <span class="schedule-label">{t('workflow.acceptedLinearStates')}</span>
                      <div class="state-grid">
                        {#each linearStates as state (state.id)}
                          <label>
                            <input
                              type="checkbox"
                              checked={detailsNode.data.filterStateIds.includes(state.id)}
                              onchange={(event) =>
                                toggleLinearState(
                                  detailsNode.id,
                                  state.id,
                                  (event.currentTarget as HTMLInputElement).checked
                                )}
                            />
                            <span>{state.team_key || state.team_name} · {state.name}</span>
                          </label>
                        {/each}
                      </div>
                    </div>
                    {#if detailsNode.data.integrationLastSyncedAt}
                      <p>
                        {t('workflow.lastReconciliation', {
                          value: detailsNode.data.integrationLastSyncedAt
                        })}
                      </p>
                    {/if}
                    {#if detailsNode.data.integrationSyncError}
                      <p class="text-danger">{detailsNode.data.integrationSyncError}</p>
                    {/if}
                  {/if}
                </div>
              {/if}
            </div>
          {/if}
          {#if !detailsNode.data.system}
            <div class="access-section">
              <div>
                <h3>{t('workflow.projectRagAccess')}</h3>
                <p>{t('workflow.projectRagAccessHint')}</p>
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
                {:else}<p>{t('workflow.noEnabledRepositories')}</p>{/each}
              </div>
            </div>
          {/if}
          <div class="mt-5 flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onclick={() => onConsole(detailsNode.data.role, detailsNode.id)}
              >{t('workflow.liveConsoleButton')}</Button
            >
            <Button size="sm" variant="primary" disabled={saving || !dirty} onclick={persist}>
              <span class="flex items-center gap-1.5">
                {#if saving}<Spinner class="size-3" />{/if}
                {saving
                  ? t('workflow.saving')
                  : dirty
                    ? t('workflow.saveNodeChanges')
                    : t('workflow.saved')}
              </span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onclick={() => {
                onSelect(detailsNode.data.role, detailsNode.id);
                detailsNodeId = '';
                document.getElementById('agent-inspector')?.scrollIntoView({ behavior: 'smooth' });
              }}>{t('workflow.fullConfiguration')}</Button
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
    border: 1px solid var(--color-line) !important;
    border-radius: 12px !important;
    background: linear-gradient(145deg, var(--color-panel), var(--color-panel-alt)) !important;
    color: var(--color-heading) !important;
    box-shadow: 0 12px 30px rgb(0 0 0 / 28%);
    transition:
      border-color 160ms ease,
      box-shadow 160ms ease,
      transform 160ms ease;
  }
  :global(.workflow-node:hover),
  :global(.workflow-node.selected) {
    border-color: var(--color-brand-2) !important;
    box-shadow:
      0 0 0 3px color-mix(in srgb, var(--color-brand-2) 15%, transparent),
      0 16px 34px rgb(0 0 0 / 32%);
  }
  :global(.workflow-node.running) {
    border-color: var(--color-accent) !important;
    animation: agent-running 1.4s ease-in-out infinite;
  }
  :global(.workflow-node.disabled) {
    border-style: dashed !important;
    opacity: 0.72;
  }
  @keyframes agent-running {
    50% {
      box-shadow:
        0 0 0 7px color-mix(in srgb, var(--color-accent) 12%, transparent),
        0 16px 34px rgb(0 0 0 / 32%);
    }
  }
  :global(.svelte-flow__edge-path) {
    stroke-width: 2.2;
  }
  :global(.route-neutral .svelte-flow__edge-path) {
    stroke: var(--color-muted);
  }
  :global(.route-processing .svelte-flow__edge-path) {
    stroke: var(--color-brand-2);
    stroke-width: 3;
    filter: drop-shadow(0 0 4px color-mix(in srgb, var(--color-brand-2) 65%, transparent));
  }
  :global(.svelte-flow__handle) {
    width: 11px;
    height: 11px;
    border: 2px solid var(--color-surface);
    background: var(--color-brand-2);
  }
  .add-button {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    border: 1px solid var(--color-brand);
    border-radius: 0.65rem;
    background: linear-gradient(120deg, var(--color-brand), var(--color-brand-2));
    padding: 0.55rem 0.8rem;
    color: var(--color-heading);
    font-size: 0.75rem;
    font-weight: 700;
    box-shadow: 0 5px 16px color-mix(in srgb, var(--color-brand) 22%, transparent);
  }
  .advanced-settings summary {
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 750;
  }
  .advanced-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.7rem;
    margin-top: 0.8rem;
  }
  .advanced-grid label {
    display: grid;
    gap: 0.32rem;
  }
  .advanced-grid label > span {
    color: var(--color-muted);
    font-size: 0.66rem;
    font-weight: 700;
  }
  .advanced-grid input,
  .advanced-grid select {
    width: 100%;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-bg);
    padding: 0.55rem;
    color: var(--color-text);
    font-size: 0.74rem;
  }
  .range-field {
    align-content: start;
    min-height: 5.1rem;
    border: 1px solid var(--color-line);
    border-radius: 0.65rem;
    background: color-mix(in srgb, var(--color-panel-alt) 65%, transparent);
    padding: 0.7rem;
  }
  .range-field > span {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .range-field > span b {
    color: var(--color-heading);
    font-size: 0.69rem;
  }
  .range-field > small {
    color: var(--color-muted);
    font-size: 0.57rem;
    letter-spacing: 0.01em;
  }
  .advanced-grid input.range {
    appearance: none;
    height: 0.34rem;
    margin: 0.55rem 0 0.25rem;
    border: 0;
    border-radius: 999px;
    background: linear-gradient(
      to right,
      var(--color-brand) 0 var(--range),
      var(--color-line) var(--range) 100%
    );
    padding: 0;
    cursor: pointer;
  }
  input.range::-webkit-slider-thumb {
    appearance: none;
    width: 1rem;
    height: 1rem;
    border: 2px solid var(--color-panel);
    border-radius: 50%;
    background: var(--color-brand-2);
    box-shadow: 0 1px 5px rgb(0 0 0/0.3);
  }
  input.range::-moz-range-thumb {
    width: 0.8rem;
    height: 0.8rem;
    border: 2px solid var(--color-panel);
    border-radius: 50%;
    background: var(--color-brand-2);
    box-shadow: 0 1px 5px rgb(0 0 0/0.3);
  }
  .range-switch {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-top: 0.45rem;
  }
  .range-switch input {
    width: 0.9rem;
    height: 0.9rem;
    padding: 0;
  }
  .range-switch small {
    color: var(--color-muted);
    font-size: 0.62rem;
  }
  .enabled-toggle {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    margin-top: 0.8rem;
    border: 1px solid var(--color-line);
    border-radius: 0.6rem;
    padding: 0.65rem;
  }
  .enabled-toggle span {
    display: grid;
    gap: 0.1rem;
    font-size: 0.75rem;
  }
  .enabled-toggle small {
    color: var(--color-muted);
    font-size: 0.64rem;
  }
  @media (max-width: 600px) {
    .advanced-grid {
      grid-template-columns: 1fr;
    }
  }
  .add-button:hover {
    border-color: var(--color-brand-2);
    filter: brightness(1.08);
  }
  .add-menu {
    position: absolute;
    z-index: 30;
    top: calc(100% + 0.55rem);
    left: 0;
    width: 250px;
    border: 1px solid var(--color-line);
    border-radius: 0.75rem;
    background: var(--color-panel-alt);
    padding: 0.4rem;
    box-shadow: 0 20px 50px rgb(0 0 0 / 55%);
  }
  .menu-title {
    padding: 0.45rem 0.55rem;
    color: var(--color-muted);
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
    color: var(--color-heading);
    text-align: left;
  }
  .role-option:hover {
    background: color-mix(in srgb, var(--color-brand-2) 12%, var(--color-panel-alt));
    color: var(--color-heading);
  }
  .role-option small {
    display: block;
    color: var(--color-muted);
    font-size: 0.58rem;
    font-weight: 400;
  }
  .role-icon {
    display: grid;
    width: 1.8rem;
    height: 1.8rem;
    place-items: center;
    border-radius: 0.45rem;
    background: color-mix(in srgb, var(--color-brand-2) 15%, transparent);
    color: var(--color-brand-2);
    font-size: 0.55rem;
    font-weight: 800;
  }
  .node-menu {
    position: fixed;
    z-index: 80;
    width: 205px;
    overflow: hidden;
    border: 1px solid var(--color-line);
    border-radius: 0.7rem;
    background: var(--color-panel-alt);
    box-shadow: 0 18px 50px rgb(0 0 0 / 60%);
  }
  .node-menu button {
    display: flex;
    width: 100%;
    justify-content: space-between;
    padding: 0.65rem 0.75rem;
    color: var(--color-heading);
    font-size: 0.7rem;
    text-align: left;
  }
  .node-menu button:hover {
    background: color-mix(in srgb, var(--color-brand-2) 12%, var(--color-panel-alt));
    color: var(--color-heading);
  }
  .node-menu button.danger {
    color: var(--color-danger);
  }
  .node-menu button:disabled {
    color: var(--color-muted);
    cursor: not-allowed;
  }
  .direction-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid var(--color-line);
    border-radius: 0.45rem;
    background: var(--color-panel-alt);
    padding: 0.3rem 0.5rem;
    color: var(--color-heading);
    font-size: 0.62rem;
  }
  .direction-summary span {
    color: var(--color-brand-2);
    font-size: 0.9rem;
  }
  .canvas-legend {
    position: absolute;
    right: 0.8rem;
    bottom: 0.65rem;
    z-index: 5;
    display: flex;
    gap: 0.8rem;
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: color-mix(in srgb, var(--color-surface) 88%, transparent);
    padding: 0.4rem 0.55rem;
    color: var(--color-muted);
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
    background: var(--color-muted);
  }
  .canvas-legend i.processing {
    background: var(--color-brand-2);
    box-shadow: 0 0 5px var(--color-brand-2);
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
    border: 1px solid var(--color-line);
    border-radius: 1rem;
    background: var(--color-panel-alt);
    box-shadow: 0 30px 90px rgb(0 0 0 / 65%);
  }
  .details-modal > header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    border-bottom: 1px solid var(--color-line);
    padding: 1rem 1.2rem;
  }
  .details-modal > header > button {
    margin-left: auto;
    border-radius: 0.4rem;
    padding: 0.2rem 0.5rem;
    color: var(--color-muted);
    font-size: 1.2rem;
  }
  .details-modal > header > button:hover {
    background: color-mix(in srgb, var(--color-brand-2) 12%, var(--color-panel-alt));
    color: var(--color-heading);
  }
  .details-avatar {
    display: grid;
    width: 2.35rem;
    height: 2.35rem;
    place-items: center;
    border: 1px solid color-mix(in srgb, var(--color-brand-2) 35%, transparent);
    border-radius: 0.65rem;
    background: color-mix(in srgb, var(--color-brand-2) 18%, transparent);
    color: var(--color-brand-2);
    font-size: 0.65rem;
    font-weight: 800;
  }
  .nickname-label {
    display: block;
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .nickname-label span {
    float: right;
    color: var(--color-muted);
  }
  .nickname-label input {
    display: block;
    width: 100%;
    margin-top: 0.45rem;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    background: var(--color-input);
    padding: 0.75rem;
    color: var(--color-heading);
    outline: none;
    font-size: 0.85rem;
  }
  .nickname-label input:focus {
    border-color: var(--color-brand-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand-2) 12%, transparent);
  }
  .details-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1px;
    margin-top: 1rem;
    overflow: hidden;
    border: 1px solid var(--color-line);
    border-radius: 0.65rem;
    background: var(--color-line);
  }
  .details-grid div {
    min-width: 0;
    background: var(--color-panel-alt);
    padding: 0.75rem;
  }
  .details-grid span {
    display: block;
    color: var(--color-muted);
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: 0.11em;
  }
  .details-grid b {
    display: block;
    overflow: hidden;
    margin-top: 0.25rem;
    color: var(--color-heading);
    font-size: 0.68rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .access-section {
    margin-top: 1rem;
    border-top: 1px solid var(--color-line);
    padding-top: 1rem;
  }
  .access-section h3 {
    color: var(--color-heading);
    font-size: 0.75rem;
    font-weight: 650;
  }
  .access-section > div > p {
    margin-top: 0.15rem;
    color: var(--color-muted);
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
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    padding: 0.55rem;
    color: var(--color-heading);
    font-size: 0.65rem;
  }
  .access-list label:hover {
    border-color: var(--color-brand-2);
    background: color-mix(in srgb, var(--color-brand-2) 10%, var(--color-panel-alt));
  }
  .access-list small {
    display: block;
    color: var(--color-muted);
    font-size: 0.52rem;
  }
  .access-list > p {
    color: var(--color-muted);
    font-size: 0.65rem;
  }
  .integration-schedule {
    display: grid;
    gap: 0.8rem;
    margin-top: 1rem;
    border-top: 1px solid var(--color-line);
    padding-top: 1rem;
  }
  .integration-schedule > label {
    display: grid;
    gap: 0.35rem;
    color: var(--color-muted);
    font-size: 0.7rem;
    font-weight: 700;
  }
  .integration-schedule select {
    width: 100%;
    border: 1px solid var(--color-line);
    border-radius: 0.55rem;
    background: var(--color-input);
    padding: 0.65rem;
    color: var(--color-heading);
  }
  .schedule-label {
    color: var(--color-muted);
    font-size: 0.7rem;
    font-weight: 700;
  }
  .state-grid {
    display: grid;
    max-height: 10rem;
    gap: 0.35rem;
    margin-top: 0.4rem;
    overflow: auto;
  }
  .state-grid label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--color-heading);
    font-size: 0.7rem;
  }
  .model-status {
    border: 1px solid var(--color-line);
    border-radius: 999px;
    padding: 0.22rem 0.45rem;
    color: var(--color-muted);
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: 0.08em;
  }
  .model-status.available {
    border-color: color-mix(in srgb, var(--color-accent) 35%, transparent);
    color: var(--color-accent);
  }
  .model-status.invalid {
    border-color: color-mix(in srgb, var(--color-danger) 35%, transparent);
    color: var(--color-danger);
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
    border: 1px solid var(--color-line);
    border-radius: 0.5rem;
    background: var(--color-input);
    padding: 0.62rem 0.7rem;
    color: var(--color-heading);
    outline: none;
    font-size: 0.68rem;
  }
  .model-controls select:focus,
  .model-controls input:focus,
  .access-section textarea:focus {
    border-color: var(--color-brand-2);
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
