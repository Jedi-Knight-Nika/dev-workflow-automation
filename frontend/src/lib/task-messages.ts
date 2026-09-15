import type { TaskMessage } from '$lib/types';

/** Combine polling/pagination results; incoming records win and IDs remain ordered. */
export function mergeTaskMessages(
  existing: readonly TaskMessage[],
  incoming: readonly TaskMessage[]
): TaskMessage[] {
  const messages = new Map(existing.map((message) => [message.id, message]));
  for (const message of incoming) messages.set(message.id, message);
  return [...messages.values()].sort((a, b) => a.id - b.id);
}
