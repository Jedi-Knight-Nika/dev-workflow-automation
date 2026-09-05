import { api } from '$lib/api';
import type { AgentConfig, ProviderCatalog } from '$lib/types';

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
