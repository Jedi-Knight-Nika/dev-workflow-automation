import { describe, expect, it } from 'vitest';
import { isActiveNavItem, NAV_ITEMS } from './nav';

describe('isActiveNavItem', () => {
  it('matches the dashboard only on an exact root path', () => {
    expect(isActiveNavItem('/', '/')).toBe(true);
    expect(isActiveNavItem('/tasks', '/')).toBe(false);
  });

  it('matches nested routes under a section as a prefix', () => {
    expect(isActiveNavItem('/tasks/abc-123', '/tasks')).toBe(true);
    expect(isActiveNavItem('/tasks', '/tasks')).toBe(true);
  });

  it('does not match unrelated sections', () => {
    expect(isActiveNavItem('/repositories', '/tasks')).toBe(false);
  });

  it('does not treat a section as a prefix of a similarly named one', () => {
    expect(isActiveNavItem('/tasksomething', '/tasks')).toBe(false);
  });
});

describe('NAV_ITEMS', () => {
  it('has a unique href per entry', () => {
    const hrefs = NAV_ITEMS.map((item) => item.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});
