import { expect, it } from 'vitest';
import { safeExternalUrl, taskDescriptionParts } from './task-links';
it('keeps useful links while shortening their visible labels', () => {
  const href = 'https://trello.com/c/abc/very-long-ticket-slug';
  const parts = taskDescriptionParts(`See ${href}. Keep this requirement.`);
  expect(parts.find((part) => part.href)?.label).toBe('trello.com');
  expect(parts.find((part) => part.href)?.href).toBe(href);
  expect(parts.at(-1)?.text).toContain('Keep this requirement.');
});
it('removes only a duplicate source line, not other task references', () => {
  const href = 'https://trello.com/c/abc';
  const parts = taskDescriptionParts(
    `Requirements\nTrello: ${href}\nDocs: https://example.com/docs`,
    href
  );
  expect(parts.filter((part) => part.href).map((part) => part.href)).toEqual([
    'https://example.com/docs'
  ]);
});
it('rejects unsafe external protocols', () => {
  expect(safeExternalUrl('javascript:alert(1)')).toBeNull();
  expect(safeExternalUrl('data:text/html,test')).toBeNull();
});
