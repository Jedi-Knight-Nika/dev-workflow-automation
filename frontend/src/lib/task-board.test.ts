import { describe, expect, it } from 'vitest';
import { priorityLabel, tasksByColumn, formatEstimate, parseEstimate } from './task-board';
import type { Task } from './types';
const task = (status: string): Task =>
  ({ id: status, status, stage: 'INTAKE', title: status, priority: 3 }) as Task;
describe('task board', () => {
  it('groups canonical statuses', () => {
    const columns = tasksByColumn([task('NEW'), task('ACTIVE'), task('FAILED'), task('MERGED')]);
    for (const id of ['backlog', 'progress', 'attention', 'done'])
      expect(columns.find((column) => column.id === id)?.tasks).toHaveLength(1);
  });
  it('names priorities', () => expect(priorityLabel(0)).toBe('Urgent'));
  it.each([
    [null, 'Unestimated'],
    [undefined, 'Unestimated'],
    [0, '0 story points'],
    [0.5, '0.5 story points'],
    [1, '1 story point'],
    [7.25, '7.25 story points']
  ] as const)('formats %s without rounding', (value, expected) =>
    expect(formatEstimate(value)).toBe(expected)
  );
  it('preserves blank, zero and fractional input', () => {
    expect(parseEstimate(' ')).toBeNull();
    expect(parseEstimate('0')).toBe(0);
    expect(parseEstimate('0.5')).toBe(0.5);
    expect(() => parseEstimate('-1')).toThrow();
    expect(() => parseEstimate('Infinity')).toThrow();
  });
});
