import { api } from '$lib/api';
import type {
  GitHubInstallationAccount,
  Integration,
  LinearWorkflowState,
  TrelloBoard,
  TrelloList,
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

export function requestIntegrationSync(providerName: string): Promise<Integration> {
  return api<Integration>(`/integrations/${providerName}/sync`, { method: 'POST' });
}

export function getGithubAppInstallUrl(): Promise<{ url: string }> {
  return api<{ url: string }>('/github/app/install-url');
}

export function getGithubInstallationAccount(): Promise<GitHubInstallationAccount> {
  return api<GitHubInstallationAccount>('/github/app/account');
}

export function listLinearWorkflowStates(): Promise<LinearWorkflowState[]> {
  return api<LinearWorkflowState[]>('/linear/workflow-states');
}

export function listTrelloBoards(): Promise<TrelloBoard[]> {
  return api<TrelloBoard[]>('/trello/boards');
}

export function listTrelloLists(boardId: string): Promise<TrelloList[]> {
  return api<TrelloList[]>(`/trello/boards/${encodeURIComponent(boardId)}/lists`);
}
