import { getTheme } from './theme.svelte';

export type AccentId = 'purple' | 'blue' | 'green' | 'yellow' | 'pink' | 'teal';
export type AccentSelection = AccentId | 'custom';

type AccentColors = { brand: string; brand2: string };
type AccentPair = { dark: AccentColors; light: AccentColors };

export const ACCENT_ORDER: AccentId[] = ['purple', 'blue', 'green', 'yellow', 'pink', 'teal'];

const PRESETS: Record<AccentId, AccentPair> = {
  purple: {
    dark: { brand: '#b26bff', brand2: '#3fd8ff' },
    light: { brand: '#7c3aed', brand2: '#0891b2' }
  },
  blue: {
    dark: { brand: '#3fa9ff', brand2: '#22d3ee' },
    light: { brand: '#2563eb', brand2: '#0e7490' }
  },
  green: {
    dark: { brand: '#4ade80', brand2: '#2dd4bf' },
    light: { brand: '#16a34a', brand2: '#0d9488' }
  },
  yellow: {
    dark: { brand: '#fbbf24', brand2: '#fb923c' },
    light: { brand: '#b45309', brand2: '#c2410c' }
  },
  pink: {
    dark: { brand: '#fb7185', brand2: '#e879f9' },
    light: { brand: '#be123c', brand2: '#a21caf' }
  },
  teal: {
    dark: { brand: '#2dd4bf', brand2: '#38bdf8' },
    light: { brand: '#0d9488', brand2: '#0369a1' }
  }
};

// Tuning per theme mode for the custom hue slider - matched by eye to the
// lightness/saturation the fixed presets already use, so a custom pick reads
// as "one of the family" rather than a different visual weight.
const CUSTOM_TUNING = {
  dark: { brandS: 88, brandL: 72, brand2S: 85, brand2L: 62 },
  light: { brandS: 80, brandL: 48, brand2S: 80, brand2L: 36 }
} as const;
const CUSTOM_BRAND2_HUE_OFFSET = -60;

const STORAGE_KEY = 'accent';
const HUE_STORAGE_KEY = 'accentHue';
const DEFAULT_HUE = 266;

let accentId = $state<AccentSelection>('purple');
let customHue = $state(DEFAULT_HUE);

export function getAccentId(): AccentSelection {
  return accentId;
}

export function getCustomHue(): number {
  return customHue;
}

function hslToHex(h: number, s: number, l: number): string {
  const hue = ((h % 360) + 360) % 360;
  const sat = s / 100;
  const light = l / 100;
  const c = (1 - Math.abs(2 * light - 1)) * sat;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = light - c / 2;
  let [r, g, b] = [0, 0, 0];
  if (hue < 60) [r, g, b] = [c, x, 0];
  else if (hue < 120) [r, g, b] = [x, c, 0];
  else if (hue < 180) [r, g, b] = [0, c, x];
  else if (hue < 240) [r, g, b] = [0, x, c];
  else if (hue < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const toHex = (value: number) =>
    Math.round((value + m) * 255)
      .toString(16)
      .padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function customColors(hue: number): AccentColors {
  const tuning = CUSTOM_TUNING[getTheme()];
  return {
    brand: hslToHex(hue, tuning.brandS, tuning.brandL),
    brand2: hslToHex(hue + CUSTOM_BRAND2_HUE_OFFSET, tuning.brand2S, tuning.brand2L)
  };
}

function currentColors(): AccentColors {
  return accentId === 'custom' ? customColors(customHue) : PRESETS[accentId][getTheme()];
}

function applyAccent(): void {
  if (typeof document === 'undefined') return;
  const colors = currentColors();
  document.documentElement.style.setProperty('--color-brand', colors.brand);
  document.documentElement.style.setProperty('--color-brand-2', colors.brand2);
}

export function setAccentId(next: AccentId): void {
  accentId = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable, choice just won't persist */
  }
  applyAccent();
}

export function setCustomHue(hue: number): void {
  customHue = Math.max(0, Math.min(360, hue));
  accentId = 'custom';
  try {
    localStorage.setItem(STORAGE_KEY, 'custom');
    localStorage.setItem(HUE_STORAGE_KEY, String(customHue));
  } catch {
    /* storage unavailable, choice just won't persist */
  }
  applyAccent();
}

export function initAccent(): void {
  let storedId: string | null = null;
  let storedHue: string | null = null;
  try {
    storedId = localStorage.getItem(STORAGE_KEY);
    storedHue = localStorage.getItem(HUE_STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
  if (storedId === 'custom') {
    accentId = 'custom';
    const hue = Number(storedHue);
    if (Number.isFinite(hue)) customHue = Math.max(0, Math.min(360, hue));
  } else if (storedId && ACCENT_ORDER.includes(storedId as AccentId)) {
    accentId = storedId as AccentId;
  }
  applyAccent();
}

export function reapplyAccentForTheme(): void {
  applyAccent();
}

export function accentPreview(id: AccentId): AccentColors {
  return PRESETS[id][getTheme()];
}

export function getAccentColors(): AccentColors {
  return currentColors();
}

export function customHuePreview(hue: number): AccentColors {
  return customColors(hue);
}
