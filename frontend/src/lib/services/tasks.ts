import { api } from '$lib/api';
import type {
  Job,
  LiveExecution,
  NativeRun,
  Task,
  TaskEvent,
  TaskMetrics,
  TaskMessage,
  TaskMessagePage,
  ValidationRecord
} from '$lib/types';

export type CreateTaskInput = {
  title: string;
  description: string;
  priority: number;
  repository_id?: string | null;
  start_work: boolean;
  external_key?: string | null;
  project_name?: string | null;
  labels?: string[];
  estimate?: number | null;
  due_at?: string | null;
};
export type TaskCommand = 'pause' | 'cancel' | 'takeover' | 'resume' | 'archive';
export type TaskFilters = {
  search?: string;
  status?: string[];
  provider?: string;
  repository_id?: string;
  priority?: number[];
  created_from?: string;
  created_to?: string;
  due_from?: string;
  due_to?: string;
  assignee?: string;
  team?: string;
  project?: string;
  label?: string;
  provider_state?: string;
  assigned_team_id?: string;
  unassigned?: boolean;
  sort?: 'priority' | 'created' | 'updated' | 'due';
  direction?: 'asc' | 'desc';
};
export function listTasks(filters: TaskFilters = {}): Promise<Task[]> {
  const query = new URLSearchParams({ limit: '500' });
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === '' || (Array.isArray(value) && value.length === 0))
      continue;
    if (Array.isArray(value)) value.forEach((item) => query.append(key, String(item)));
    else query.set(key, String(value));
  }
  return api<Task[]>('/tasks?' + query.toString());
}
export const getTask = (id: string) => api<Task>('/tasks/' + id);
export const createTask = (input: CreateTaskInput) =>
  api<Task>('/tasks', { method: 'POST', body: JSON.stringify(input) });
export const listTaskJobs = (id: string) => api<Job[]>('/tasks/' + id + '/jobs');
export const listTaskRuns = (id: string) => api<NativeRun[]>('/tasks/' + id + '/runs');
export const getLiveExecution = (id: string) =>
  api<LiveExecution | null>('/tasks/' + id + '/live-execution');
export const listTaskEvents = (id: string) => api<TaskEvent[]>('/tasks/' + id + '/events');
export const listTaskValidations = (id: string) =>
  api<ValidationRecord[]>('/tasks/' + id + '/validations');
export const getTaskMetrics = (id: string) => api<TaskMetrics>('/tasks/' + id + '/metrics');
export function listTaskMessages(id: string, beforeId?: number): Promise<TaskMessagePage> {
  const query = new URLSearchParams({ limit: '50' });
  if (beforeId) query.set('before_id', String(beforeId));
  return api<TaskMessagePage>('/tasks/' + id + '/messages?' + query.toString());
}
export const addTaskMessage = (id: string, body: string, replyToId?: number) =>
  api<TaskMessage>('/tasks/' + id + '/messages', {
    method: 'POST',
    body: JSON.stringify({ body, reply_to_id: replyToId ?? null })
  });
export const runTaskCommand = (id: string, command: TaskCommand) =>
  api<Task>('/tasks/' + id + '/' + command, { method: 'POST' });
