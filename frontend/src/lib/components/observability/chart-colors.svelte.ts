import { getTheme } from '$lib/theme.svelte';

const PALETTES = {
  dark: {
    brand: '#b26bff',
    brand2: '#3fd8ff',
    warning: '#ffb648',
    accent: '#4ade80',
    danger: '#ff5f7a',
    line: '#262336',
    muted: '#9691ab'
  },
  light: {
    brand: '#7c3aed',
    brand2: '#0891b2',
    warning: '#b45309',
    accent: '#16a34a',
    danger: '#dc2626',
    line: '#ddd9f0',
    muted: '#6b6478'
  }
} as const;

export function chartColors() {
  return PALETTES[getTheme()];
}

export function categoricalPalette(): string[] {
  const c = chartColors();
  return [c.brand2, c.brand, c.warning, c.accent];
}

export function hexAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255,
    g = (n >> 8) & 255,
    b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
