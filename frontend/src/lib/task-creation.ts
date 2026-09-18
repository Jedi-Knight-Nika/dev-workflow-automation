import type { CreateTaskInput } from '$lib/services/tasks';

const STORAGE_KEY = 'task-creation-request';

/** Session-scoped so a lost response can still be deduped after a remount or back-navigation. */
function readStored(): { fingerprint: string; requestId: string } | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function writeStored(value: { fingerprint: string; requestId: string } | null) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode, quota): idempotency falls back to in-memory only.
  }
}

export function createTaskRequest() {
  const stored = readStored();
  let previous = stored?.fingerprint ?? '';
  let requestId = stored?.requestId ?? '';
  return {
    prepare(input: CreateTaskInput): CreateTaskInput {
      const serialized = JSON.stringify(input);
      if (!requestId || serialized !== previous) {
        previous = serialized;
        requestId = crypto.randomUUID();
        writeStored({ fingerprint: previous, requestId });
      }
      return { ...input, request_id: requestId };
    },
    complete() {
      previous = '';
      requestId = '';
      writeStored(null);
    }
  };
}
