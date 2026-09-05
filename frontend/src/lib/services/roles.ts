import { api } from '$lib/api';
import type { Role } from '$lib/types';

export type RoleInput = Omit<
  Role,
  'id' | 'built_in' | 'version' | 'active_agents' | 'created_at' | 'updated_at'
>;

export const listRoles = () => api<Role[]>('/roles');
export const getRole = (id: string) => api<Role>(`/roles/${id}`);
export const createRole = (input: RoleInput) =>
  api<Role>('/roles', { method: 'POST', body: JSON.stringify(input) });
export const updateRole = (id: string, input: RoleInput) =>
  api<Role>(`/roles/${id}`, { method: 'PUT', body: JSON.stringify(input) });
export const cloneRole = (id: string, name: string) =>
  api<Role>(`/roles/${id}/clone`, { method: 'POST', body: JSON.stringify({ name }) });
export const disableRole = (id: string) => api<Role>(`/roles/${id}/disable`, { method: 'POST' });
export const deleteRole = (id: string) => api<void>(`/roles/${id}`, { method: 'DELETE' });
export const listRolePermissions = () => api<string[]>('/roles/catalog/permissions');
export const listRoleCapabilities = () => api<string[]>('/roles/catalog/capabilities');
