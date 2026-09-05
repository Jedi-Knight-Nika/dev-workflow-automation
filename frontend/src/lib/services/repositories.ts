import { api } from '$lib/api';
import type { DiscoveredRepository, KnowledgeResult, Repository } from '$lib/types';

export type AddRepositoryInput = {
  provider: string;
  external_repo_id: string;
  owner: string;
  name: string;
  clone_url: string;
  default_branch: string;
};

export function listRepositories(): Promise<Repository[]> {
  return api<Repository[]>('/repositories');
}

export function addRepository(input: AddRepositoryInput): Promise<Repository> {
  return api<Repository>('/repositories', { method: 'POST', body: JSON.stringify(input) });
}

export function discoverGithubRepositories(): Promise<DiscoveredRepository[]> {
  return api<DiscoveredRepository[]>('/github/repositories');
}

export function queueRepositoryIndex(repositoryId: string): Promise<unknown> {
  return api(`/repositories/${repositoryId}/index`, { method: 'POST' });
}

export function setRepositoryEnabled(repositoryId: string, enabled: boolean): Promise<unknown> {
  return api(`/repositories/${repositoryId}/enabled?enabled=${enabled}`, { method: 'PATCH' });
}

export function deleteRepository(repositoryId: string): Promise<void> {
  return api<void>(`/repositories/${repositoryId}`, { method: 'DELETE' });
}

export function searchRepositoryKnowledge(
  repositoryId: string,
  query: string
): Promise<KnowledgeResult[]> {
  return api<KnowledgeResult[]>(
    `/repositories/${repositoryId}/search?query=${encodeURIComponent(query)}`
  );
}
