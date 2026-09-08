import { api } from '$lib/api';
import type { TaskAssignment, Team } from '$lib/types';

export type TeamInput = Pick<
  Team,
  'name' | 'description' | 'enabled' | 'max_concurrent_tasks' | 'repository_ids'
>;

export const listTeams = () => api<Team[]>('/teams');
export const createTeam = (input: TeamInput) =>
  api<Team>('/teams', { method: 'POST', body: JSON.stringify(input) });
export const updateTeam = (id: string, input: TeamInput) =>
  api<Team>(`/teams/${id}`, { method: 'PUT', body: JSON.stringify(input) });
export const archiveTeam = (id: string) => api<void>(`/teams/${id}`, { method: 'DELETE' });
export type ShutdownTeamResult = { cancelled_jobs: number; paused_tasks: number };
export const shutdownTeam = (id: string) =>
  api<ShutdownTeamResult>(`/teams/${id}/shutdown`, { method: 'POST' });
export const wakeTeam = (id: string) =>
  api<{ created_jobs: number }>(`/teams/${id}/wake`, { method: 'POST' });
export const listTeamAssignments = (id: string) =>
  api<TaskAssignment[]>(`/teams/${id}/assignments`);
export const assignTaskToTeam = (teamId: string, taskId: string, startWork = false) =>
  api<TaskAssignment>(`/teams/${teamId}/assignments`, {
    method: 'POST',
    body: JSON.stringify({ task_id: taskId, reason: 'manual', start_work: startWork })
  });
export const unassignTask = (taskId: string) =>
  api<void>(`/teams/assignments/${taskId}`, { method: 'DELETE' });
