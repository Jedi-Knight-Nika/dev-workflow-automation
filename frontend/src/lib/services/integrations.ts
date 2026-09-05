import { api } from '$lib/api';
import type {
  GitHubInstallationAccount,
  Integration,
  LinearWorkflowState,
  LinearMember,
  WebhookHealth
} from '$lib/types';

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

export function testIntegration(providerName: string): Promise<Integration> {
  return api<Integration>(`/integrations/${providerName}/test`, { method: 'POST' });
}

export function getGithubAppInstallUrl(): Promise<{ url: string }> {
  return api<{ url: string }>('/github/app/install-url');
}

export function getGithubAppManageUrl(): Promise<{ url: string }> {
  return api<{ url: string }>('/github/app/manage-url');
}

export function getGithubInstallationAccount(): Promise<GitHubInstallationAccount> {
  return api<GitHubInstallationAccount>('/github/app/account');
}

export function listLinearWorkflowStates(): Promise<LinearWorkflowState[]> {
  return api<LinearWorkflowState[]>('/linear/workflow-states');
}

export function listLinearMembers(): Promise<LinearMember[]> {
  return api<LinearMember[]>('/linear/members');
}
