import { api } from '$lib/api';
import type { Job, ReviewFinding, Task, TaskEvent, ValidationRecord } from '$lib/types';

export type CreateTaskInput = {
  title: string;
  description: string;
  priority: number;
  repository_id: string | null;
  enqueue_planning: boolean;
  external_key?: string | null;
};

export type CreateJobInput = {
  role: 'THINKER' | 'EXECUTOR' | 'REVIEWER';
  action: string;
  priority: number;
  payload: Record<string, unknown>;
};

export type TaskCommand = 'pause' | 'cancel' | 'takeover' | 'resume';

export function listTasks(): Promise<Task[]> {
  return api<Task[]>('/tasks');
}

export function getTask(taskId: string): Promise<Task> {
  return api<Task>(`/tasks/${taskId}`);
}

export function createTask(input: CreateTaskInput): Promise<Task> {
  return api<Task>('/tasks', { method: 'POST', body: JSON.stringify(input) });
}

export function listTaskJobs(taskId: string): Promise<Job[]> {
  return api<Job[]>(`/tasks/${taskId}/jobs`);
}

export function createTaskJob(taskId: string, input: CreateJobInput): Promise<Job> {
  return api<Job>(`/tasks/${taskId}/jobs`, { method: 'POST', body: JSON.stringify(input) });
}

export function listTaskEvents(taskId: string): Promise<TaskEvent[]> {
  return api<TaskEvent[]>(`/tasks/${taskId}/events`);
}

export function listTaskValidations(taskId: string): Promise<ValidationRecord[]> {
  return api<ValidationRecord[]>(`/tasks/${taskId}/validations`);
}

export function listTaskFindings(taskId: string): Promise<ReviewFinding[]> {
  return api<ReviewFinding[]>(`/tasks/${taskId}/findings`);
}

export function prepareTaskWorkspace(taskId: string): Promise<Task> {
  return api<Task>(`/tasks/${taskId}/workspace`, { method: 'POST' });
}

export function publishTaskPullRequest(taskId: string): Promise<unknown> {
  return api(`/tasks/${taskId}/pull-request`, { method: 'POST' });
}

export function mergeTaskPullRequest(taskId: string): Promise<unknown> {
  return api(`/tasks/${taskId}/merge`, { method: 'POST' });
}

export function retryTaskLinearSync(taskId: string): Promise<{ synchronized: boolean }> {
  return api<{ synchronized: boolean }>(`/tasks/${taskId}/linear-sync`, { method: 'POST' });
}

export function runTaskCommand(taskId: string, command: TaskCommand): Promise<Task> {
  return api<Task>(`/tasks/${taskId}/${command}`, { method: 'POST' });
}
