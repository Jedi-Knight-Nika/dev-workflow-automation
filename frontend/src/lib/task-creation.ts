import type { CreateTaskInput } from '$lib/services/tasks';

export function createTaskRequest() {
  let previous = '';
  let requestId = '';
  return {
    prepare(input: CreateTaskInput): CreateTaskInput {
      const serialized = JSON.stringify(input);
      if (!requestId || serialized !== previous) {
        previous = serialized;
        requestId = crypto.randomUUID();
      }
      return { ...input, request_id: requestId };
    },
    complete() {
      previous = '';
      requestId = '';
    }
  };
}
