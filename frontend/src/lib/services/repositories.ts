import { api } from '$lib/api';
import type { DiscoveredRepository, Repository } from '$lib/types';
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
export const listRepositories = (includeArchived = false) =>
  api<Repository[]>('/repositories?include_archived=' + includeArchived);
export const importRepositories = (repositories: AddRepositoryInput[]) =>
  api<Repository[]>('/repositories/import', {
    method: 'POST',
    body: JSON.stringify({ repositories })
  });
export const addRepository = (input: AddRepositoryInput) =>
  api<Repository>('/repositories', { method: 'POST', body: JSON.stringify(input) });
export const discoverGithubRepositories = () => api<DiscoveredRepository[]>('/github/repositories');
export const setRepositoryEnabled = (id: string, enabled: boolean) =>
  api<Repository>('/repositories/' + id + '/enabled?enabled=' + enabled, { method: 'PATCH' });
export const setRepositoryArchived = (id: string, archived: boolean) =>
  api<Repository>('/repositories/' + id + '/archived?archived=' + archived, { method: 'PATCH' });
export const getRepositoryDependencies = (id: string) =>
  api<RepositoryDependencies>('/repositories/' + id + '/dependencies');
export const deleteRepository = (id: string) =>
  api<void>('/repositories/' + id, { method: 'DELETE' });
