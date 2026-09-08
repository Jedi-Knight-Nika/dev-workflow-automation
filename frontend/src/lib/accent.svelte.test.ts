import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ACCENT_CYCLE_MS,
  ACCENT_ORDER,
  accentPreview,
  customHuePreview,
  getAccentColors,
  getAccentId,
  getCustomHue,
  initAccent,
  setAccentId,
  setCustomHue
} from './accent.svelte';
import { actionColors, contrastRatio, onColor } from './color-contrast';
import { setTheme } from './theme.svelte';

describe('appearance preferences', () => {
  let dispose: (() => void) | undefined;
  let motion: EventTarget & { matches: boolean };
  let documentState: EventTarget & { hidden: boolean };
  let stored: Map<string, string>;

  beforeEach(() => {
    vi.useFakeTimers();
    stored = new Map();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value)
    });
    motion = Object.assign(new EventTarget(), { matches: false });
    vi.stubGlobal('window', { matchMedia: () => motion });
    documentState = Object.assign(new EventTarget(), {
      hidden: false,
      documentElement: { dataset: {}, style: { setProperty: vi.fn() } }
    });
    vi.stubGlobal('document', documentState);
    setAccentId('purple');
    setTheme('dark');
  });

  afterEach(() => {
    dispose?.();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('cycles presets with one timer, persists the mode, and stops on a manual choice', () => {
    dispose = initAccent();
    expect(vi.getTimerCount()).toBe(0);
    setAccentId('cycle');
    expect(stored.get('accent')).toBe('cycle');
    for (let index = 1; index <= ACCENT_ORDER.length; index++) {
      vi.advanceTimersByTime(ACCENT_CYCLE_MS);
      expect(getAccentColors()).toEqual(accentPreview(ACCENT_ORDER[index % ACCENT_ORDER.length]));
      expect(vi.getTimerCount()).toBe(1);
    }
    setAccentId('pink');
    expect(vi.getTimerCount()).toBe(0);
    setAccentId('cycle');
    setCustomHue(180);
    expect(getAccentId()).toBe('custom');
    expect(vi.getTimerCount()).toBe(0);
    setCustomHue(Number.NaN);
    expect(getCustomHue()).toBe(180);
  });

  it('restores cycling, pauses while hidden or reduced motion, and removes listeners on disposal', () => {
    stored.set('accent', 'cycle');
    dispose = initAccent();
    expect(getAccentId()).toBe('cycle');
    const before = getAccentColors();
    documentState.hidden = true;
    documentState.dispatchEvent(new Event('visibilitychange'));
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(ACCENT_CYCLE_MS * 4);
    expect(getAccentColors()).toEqual(before);
    documentState.hidden = false;
    documentState.dispatchEvent(new Event('visibilitychange'));
    expect(vi.getTimerCount()).toBe(1);
    motion.matches = true;
    motion.dispatchEvent(new Event('change'));
    expect(vi.getTimerCount()).toBe(0);
    motion.matches = false;
    motion.dispatchEvent(new Event('change'));
    expect(vi.getTimerCount()).toBe(1);
    dispose();
    documentState.dispatchEvent(new Event('visibilitychange'));
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps solid and gradient button labels readable for every hue in both themes', () => {
    for (const theme of ['dark', 'light'] as const) {
      setTheme(theme);
      const palettes = [
        ...ACCENT_ORDER.map(accentPreview),
        ...Array.from({ length: 361 }, (_, hue) => customHuePreview(hue))
      ];
      for (const { brand, brand2 } of palettes) {
        expect(contrastRatio(brand, onColor(brand))).toBeGreaterThanOrEqual(4.5);
        const action = actionColors(brand, brand2);
        for (let step = 0; step <= 100; step++) {
          const color = `#${[1, 3, 5]
            .map((offset) => {
              const start = parseInt(action.start.slice(offset, offset + 2), 16);
              const end = parseInt(action.end.slice(offset, offset + 2), 16);
              return Math.round(start + ((end - start) * step) / 100)
                .toString(16)
                .padStart(2, '0');
            })
            .join('')}`;
          expect(contrastRatio(color, action.foreground)).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
  });
});
