import type { Task } from '$lib/types';

export const TASK_COLUMNS = [
  { id: 'backlog', label: 'Backlog', states: ['NEW', 'CONTEXT_PENDING', 'PLANNING', 'PLAN_READY'] },
  {
    id: 'progress',
    label: 'In progress',
    states: ['QUEUED_FOR_EXECUTION', 'IMPLEMENTING', 'LOCAL_VALIDATION']
  },
  { id: 'review', label: 'Review', states: ['INTERNAL_REVIEW', 'WAITING_GITHUB'] },
  { id: 'ready', label: 'Ready', states: ['READY_TO_MERGE'] },
  { id: 'done', label: 'Done', states: ['MERGED'] },
  { id: 'attention', label: 'Attention', states: ['NEEDS_HUMAN', 'FAILED', 'PAUSED', 'CANCELLED'] }
] as const;

export function tasksByColumn(tasks: Task[]) {
  return TASK_COLUMNS.map((column) => ({
    ...column,
    tasks: tasks.filter((task) => (column.states as readonly string[]).includes(task.state))
  }));
}

export function priorityLabel(priority: number): string {
  return ['Urgent', 'Critical', 'High', 'Medium', 'Low', 'No priority'][priority] ?? `P${priority}`;
}
