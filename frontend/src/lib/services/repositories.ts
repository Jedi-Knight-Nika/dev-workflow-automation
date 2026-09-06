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

export type RepositoryDependencies = {
  teams: string[];
  active_tasks: number;
  active_workspaces: number;
  task_sources: string[];
};

export function listRepositories(includeArchived = false): Promise<Repository[]> {
  return api<Repository[]>(`/repositories?include_archived=${includeArchived}`);
}

export function importRepositories(
  repositories: AddRepositoryInput[],
  prepareKnowledge = true
): Promise<Repository[]> {
  return api<Repository[]>('/repositories/import', {
    method: 'POST',
    body: JSON.stringify({ repositories, prepare_knowledge: prepareKnowledge })
  });
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

export function setRepositoryArchived(
  repositoryId: string,
  archived: boolean
): Promise<Repository> {
  return api<Repository>(`/repositories/${repositoryId}/archived?archived=${archived}`, {
    method: 'PATCH'
  });
}

export function getRepositoryDependencies(repositoryId: string): Promise<RepositoryDependencies> {
  return api<RepositoryDependencies>(`/repositories/${repositoryId}/dependencies`);
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
