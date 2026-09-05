import { api } from '$lib/api';
import type { Integration, LinearWorkflowState, WebhookHealth } from '$lib/types';

export type SaveIntegrationInput = {
  provider_type: string;
  status: string;
  configuration: Record<string, unknown>;
  credential: string | null;
};

export function listIntegrations(): Promise<Integration[]> {
  return api<Integration[]>('/integrations');
}

export function listWebhookHealth(): Promise<WebhookHealth[]> {
  return api<WebhookHealth[]>('/webhook-health');
}

export function saveIntegration(
  providerName: string,
  input: SaveIntegrationInput
): Promise<Integration> {
  return api<Integration>(`/integrations/${providerName}`, {
    method: 'PUT',
    body: JSON.stringify(input)
  });
}

export function testIntegration(providerName: string): Promise<unknown> {
  return api(`/integrations/${providerName}/test`, { method: 'POST' });
}

export function getGithubAppInstallUrl(): Promise<{ url: string }> {
  return api<{ url: string }>('/github/app/install-url');
}

export function listLinearWorkflowStates(): Promise<LinearWorkflowState[]> {
  return api<LinearWorkflowState[]>('/linear/workflow-states');
}
