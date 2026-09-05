import { api } from '$lib/api';
import type { AgentConfig, AgentKnowledge, ProviderCatalog, WorkflowGraph } from '$lib/types';

export type SaveAgentInput = {
  enabled: boolean;
  provider: string;
  model: string;
  configuration: Record<string, unknown>;
};

export function listAgents(): Promise<AgentConfig[]> {
  return api<AgentConfig[]>('/agents');
}

export function saveAgent(role: string, input: SaveAgentInput): Promise<AgentConfig> {
  return api<AgentConfig>(`/agents/${role}`, { method: 'PUT', body: JSON.stringify(input) });
}

export function discoverProviderModels(provider: string): Promise<ProviderCatalog> {
  return api<ProviderCatalog>(`/providers/${provider}/catalog`);
}

export function listAgentKnowledge(role: string): Promise<AgentKnowledge[]> {
  return api<AgentKnowledge[]>(`/agents/${role}/knowledge`);
}

export function addAgentKnowledge(
  role: string,
  input: { title: string; content: string }
): Promise<AgentKnowledge> {
  return api<AgentKnowledge>(`/agents/${role}/knowledge`, {
    method: 'POST',
    body: JSON.stringify(input)
  });
}

export function deleteAgentKnowledge(role: string, id: string): Promise<void> {
  return api<void>(`/agents/${role}/knowledge/${id}`, { method: 'DELETE' });
}

export function getWorkflow(teamId?: string): Promise<WorkflowGraph> {
  return api<WorkflowGraph>(teamId ? `/teams/${teamId}/workflow` : '/workflow');
}

export function saveWorkflow(workflow: WorkflowGraph, teamId?: string): Promise<WorkflowGraph> {
  return api<WorkflowGraph>(teamId ? `/teams/${teamId}/workflow` : '/workflow', {
    method: 'PUT',
    body: JSON.stringify(workflow)
  });
}

export function validateWorkflowNodeModel(
  nodeId: string,
  teamId?: string
): Promise<{
  node_id: string;
  status: string;
  message: string | null;
  validated_at: string;
}> {
  return api(
    teamId
      ? `/teams/${teamId}/workflow/nodes/${nodeId}/validate-model`
      : `/workflow/nodes/${nodeId}/validate-model`,
    { method: 'POST' }
  );
}
