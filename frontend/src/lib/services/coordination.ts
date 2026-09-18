import { api } from '$lib/api';

export type HumanRequest = {
  id: string;
  task_id: string;
  question: string;
  why_needed: string;
  choices: string[];
  status: string;
  answer: string | null;
  created_at: string;
};
export type Coordination = {
  mode: 'off' | 'shadow' | 'active';
  human_request: HumanRequest | null;
  runs: {
    id: string;
    status: string;
    mode: string;
    error: string | null;
    decision: { action: string; message: string; reason: string } | null;
    created_at: string;
  }[];
  actions: {
    id: string;
    type: string;
    status: string;
    error: string | null;
    review: 'CORRECT' | 'INCORRECT' | null;
  }[];
};
export type WorkQueue = {
  mode: Coordination['mode'];
  developer_slots: { busy: number; capacity: number };
  total: number;
  offset: number;
  spending: {
    today_usd: string | null;
    month_usd: string | null;
    monthly_limit_usd: string | null;
    daily_allowance_exceeded: boolean;
  };
  truncated: boolean;
  human_requests: HumanRequest[];
  recently_completed: { id: string; title: string; team: string | null; completed_at: string }[];
  entries: {
    id: string;
    title: string;
    team: string | null;
    priority: number;
    lane: string;
    stage: string;
    wait_reason: string;
  }[];
};
export const getCoordination = (id: string) => api<Coordination>(`/tasks/${id}/coordinator`);
export const getQueue = (teamId?: string, offset = 0) =>
  api<WorkQueue>((teamId ? `/queue/teams/${teamId}` : '/queue') + `?offset=${offset}`);
export const answerHumanRequest = (request: HumanRequest, answer: string) =>
  api(`/tasks/${request.task_id}/human-request/respond`, {
    method: 'POST',
    body: JSON.stringify({ request_id: request.id, answer })
  });
export const setTaskPriority = (id: string, priority: number) =>
  api(`/tasks/${id}/priority`, { method: 'POST', body: JSON.stringify({ priority }) });

export const reconcileAction = (taskId: string, actionId: string) =>
  api(`/tasks/${taskId}/actions/${actionId}/reconcile`, { method: 'POST' });

export const reviewAction = (taskId: string, actionId: string, verdict: 'CORRECT' | 'INCORRECT') =>
  api(`/tasks/${taskId}/actions/${actionId}/review`, {
    method: 'POST',
    body: JSON.stringify({ verdict })
  });
