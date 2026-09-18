import { expect, it } from 'vitest';
import { applyReplyEvent, uniqueSources } from './messages';
import type { Evidence, ObserverMessage } from './types';

const messages: ObserverMessage[] = [
  { id: 'user', role: 'user', content: 'question', sources: [] },
  { id: 'reply', role: 'assistant', content: 'partial', sources: [] }
];

it('updates only the stream reply without mutating previous messages', () => {
  const next = applyReplyEvent(
    messages,
    'reply',
    { type: 'observer.text_delta', text: ' answer' },
    'error'
  );
  expect(next[0]).toBe(messages[0]);
  expect(next[1].content).toBe('partial answer');
  expect(messages[1].content).toBe('partial');
  const completed = applyReplyEvent(
    next,
    'reply',
    { type: 'observer.completed', answer: '' },
    'error'
  );
  expect(completed[1].content).toBe('partial answer');
  expect(
    applyReplyEvent(next, 'reply', { type: 'observer.failed' }, 'unavailable')[1].content
  ).toBe('unavailable');
  expect(applyReplyEvent(messages, 'reply', { type: 'observer.tool_started' }, 'error')).toBe(
    messages
  );
});

it('keeps the first source for each name and completeness, in original order', () => {
  const source: Evidence = {
    key: 'first',
    text: 'evidence',
    source: 'database',
    complete: true,
    measured_at: null
  };
  const incomplete = { ...source, complete: false };
  expect(uniqueSources([source, { ...source, key: 'duplicate' }, incomplete])).toEqual([
    source,
    incomplete
  ]);
});
