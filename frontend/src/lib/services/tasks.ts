import { api } from '$lib/api';
import type {
  AgentCheckpoint,
  Job,
  ReviewFinding,
  Task,
  TaskEvent,
  TaskMemory,
  ValidationRecord
} from '$lib/types';

export type CreateTaskInput = {
  title: string;
  description: string;
  priority: number;
  repository_id?: string | null;
  enqueue_planning: boolean;
  external_key?: string | null;
  project_name?: string | null;
  labels?: string[];
  estimate?: number | null;
  due_at?: string | null;
};

export type CreateJobInput = {
  role: 'THINKER' | 'EXECUTOR' | 'REVIEWER';
  action: string;
  priority: number;
  payload: Record<string, unknown>;
};

export type TaskCommand = 'pause' | 'cancel' | 'takeover' | 'resume';

export type TaskFilters = {
  search?: string;
  state?: string[];
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
  return api<Task[]>(`/tasks?${query.toString()}`);
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

export function getTaskMemory(taskId: string): Promise<TaskMemory> {
  return api<TaskMemory>(`/tasks/${taskId}/memory`);
}

export function listTaskCheckpoints(taskId: string): Promise<AgentCheckpoint[]> {
  return api<AgentCheckpoint[]>(`/tasks/${taskId}/checkpoints`);
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
