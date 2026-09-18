import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTaskRequest } from './task-creation';

function stubSessionStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key)
  });
}

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

  describe('with session storage', () => {
    afterEach(() => vi.unstubAllGlobals());

    it('survives a remount so a lost response can still be deduped on retry', () => {
      stubSessionStorage();
      const first = createTaskRequest().prepare(input);
      const remounted = createTaskRequest();
      expect(remounted.prepare({ ...input }).request_id).toBe(first.request_id);
      remounted.complete();
      expect(createTaskRequest().prepare(input).request_id).not.toBe(first.request_id);
    });

    it('changes identity across a remount once the draft has changed', () => {
      stubSessionStorage();
      const first = createTaskRequest().prepare(input);
      const remounted = createTaskRequest();
      expect(remounted.prepare({ ...input, team_id: 'selected' }).request_id).not.toBe(
        first.request_id
      );
    });
  });
});
