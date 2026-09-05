import { describe, expect, it } from 'vitest';
import { priorityLabel, tasksByColumn } from './task-board';
import type { Task } from './types';

const task = (state: string): Task =>
  ({
    id: state,
    state,
    priority: 3,
    title: state,
    description: '',
    created_at: '',
    updated_at: ''
  }) as Task;

describe('task board', () => {
  it('groups workflow states into operational columns', () => {
    const columns = tasksByColumn([task('NEW'), task('IMPLEMENTING'), task('FAILED')]);
    expect(columns.find((column) => column.id === 'backlog')?.tasks).toHaveLength(1);
    expect(columns.find((column) => column.id === 'progress')?.tasks).toHaveLength(1);
    expect(columns.find((column) => column.id === 'attention')?.tasks).toHaveLength(1);
  });

  it('names priorities', () => expect(priorityLabel(0)).toBe('Urgent'));
});
