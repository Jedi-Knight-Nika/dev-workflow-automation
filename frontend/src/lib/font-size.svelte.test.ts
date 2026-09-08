import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_FONT_SIZE, getFontSize, initFontSize, setFontSize } from './font-size.svelte';

describe('font size preference', () => {
  let stored: Map<string, string>;
  const setProperty = vi.fn();

  beforeEach(() => {
    stored = new Map();
    setProperty.mockClear();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value)
    });
    vi.stubGlobal('document', { documentElement: { style: { setProperty } } });
    setFontSize(DEFAULT_FONT_SIZE);
    setProperty.mockClear();
  });

  afterEach(() => vi.unstubAllGlobals());

  it('restores a saved size and applies it to the document root', () => {
    stored.set('fontSize', '18');

    initFontSize();

    expect(getFontSize()).toBe(18);
    expect(setProperty).toHaveBeenLastCalledWith('--app-font-size', '18px');
  });

  it('clamps values to the supported range before saving and applying them', () => {
    setFontSize(99);

    expect(getFontSize()).toBe(20);
    expect(stored.get('fontSize')).toBe('20');
    expect(setProperty).toHaveBeenLastCalledWith('--app-font-size', '20px');
  });
});
