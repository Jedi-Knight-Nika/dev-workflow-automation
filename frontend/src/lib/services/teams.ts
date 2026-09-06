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
export type WakeTeamResult = {
  recovered_jobs: number;
  created_jobs: number;
  queued_jobs: number;
  running_jobs: number;
  missing_repository_tasks: number;
};
export const wakeTeam = (id: string) =>
  api<WakeTeamResult>(`/teams/${id}/wake`, { method: 'POST' });
export const listTeamAssignments = (id: string) =>
  api<TaskAssignment[]>(`/teams/${id}/assignments`);
export const assignTaskToTeam = (teamId: string, taskId: string) =>
  api<TaskAssignment>(`/teams/${teamId}/assignments`, {
    method: 'POST',
    body: JSON.stringify({ task_id: taskId, reason: 'manual' })
  });
export const unassignTask = (taskId: string) =>
  api<void>(`/teams/assignments/${taskId}`, { method: 'DELETE' });
