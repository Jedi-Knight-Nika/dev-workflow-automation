import type { Evidence, ObserverMessage, ObserverStreamEvent } from './types';

/** Update only the reply owned by this stream; unrelated conversation entries are preserved. */
export function applyReplyEvent(
  messages: ObserverMessage[],
  replyId: string,
  event: ObserverStreamEvent,
  failureMessage: string
): ObserverMessage[] {
  if (event.type === 'observer.text_delta')
    return messages.map((message) =>
      message.id === replyId
        ? { ...message, content: message.content + (event.text || '') }
        : message
    );
  if (event.type === 'observer.completed')
    return messages.map((message) =>
      message.id === replyId
        ? { ...message, content: event.answer || message.content, sources: event.sources || [] }
        : message
    );
  if (event.type === 'observer.failed')
    return messages.map((message) =>
      message.id === replyId ? { ...message, content: failureMessage } : message
    );
  return messages;
}

export function uniqueSources(sources: Evidence[]): Evidence[] {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const key = JSON.stringify([source.source, source.complete]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
