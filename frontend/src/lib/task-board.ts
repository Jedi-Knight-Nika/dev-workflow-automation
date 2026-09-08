import type { Task } from '$lib/types';

export const TASK_COLUMNS = [
  { id: 'backlog', label: 'To do', statuses: ['NEW'] },
  { id: 'progress', label: 'In progress', statuses: ['ACTIVE'] },
  { id: 'review', label: 'Waiting externally', statuses: ['WAITING_EXTERNAL'] },
  { id: 'attention', label: 'Needs attention', statuses: ['WAITING_HUMAN', 'PAUSED', 'FAILED'] },
  { id: 'done', label: 'Merged', statuses: ['MERGED'] },
  { id: 'cancelled', label: 'Cancelled', statuses: ['CANCELLED'] }
] as const;

export function tasksByColumn(tasks: Task[]) {
  return TASK_COLUMNS.map((column) => ({
    ...column,
    tasks: tasks.filter((task) => (column.statuses as readonly string[]).includes(task.status))
  }));
}
export function priorityLabel(priority: number): string {
  return ['Urgent', 'Critical', 'High', 'Medium', 'Low', 'No priority'][priority] ?? 'P' + priority;
}
export function formatEstimate(value: number | null | undefined): string {
  return value == null ? 'Unestimated' : value + (value === 1 ? ' story point' : ' story points');
}
export function parseEstimate(value: string): number | null {
  if (!value.trim()) return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0)
    throw new Error('Story points must be a non-negative number.');
  return number;
}
