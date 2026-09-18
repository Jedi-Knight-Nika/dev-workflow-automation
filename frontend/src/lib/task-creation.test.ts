import { describe, expect, it } from 'vitest';
import { createTaskRequest } from './task-creation';

describe('task creation retries', () => {
  const input = { title: 'Task', description: '', priority: 3, start_work: false };

  it('reuses an identity for retries and changes it for edited or completed requests', () => {
    const request = createTaskRequest();
    const first = request.prepare(input);
    expect(request.prepare({ ...input }).request_id).toBe(first.request_id);
    expect(request.prepare({ ...input, team_id: 'selected' }).request_id).not.toBe(
      first.request_id
    );
    const selected = request.prepare({ ...input, team_id: 'selected' });
    request.complete();
    expect(request.prepare({ ...input, team_id: 'selected' }).request_id).not.toBe(
      selected.request_id
    );
  });
});
