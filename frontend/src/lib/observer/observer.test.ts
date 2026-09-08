import { describe, expect, it } from 'vitest';
import { scopeQuery } from './api';

describe('Observer scope transport', () => {
  it('sends references rather than arbitrary metrics or model instructions', () => {
    expect(scopeQuery({ page: 'DASHBOARD' })).toBe('');
    expect(scopeQuery({ page: 'TASK', task_id: 'abc' })).toBe('?task_id=abc');
    expect(scopeQuery({ page: 'TEAM', team_id: 'xyz' })).toBe('?team_id=xyz');
  });
});
