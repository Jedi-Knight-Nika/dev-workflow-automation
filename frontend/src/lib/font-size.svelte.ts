export const DEFAULT_FONT_SIZE = 16;
export const MIN_FONT_SIZE = 14;
export const MAX_FONT_SIZE = 20;

const STORAGE_KEY = 'fontSize';

let fontSize = $state(DEFAULT_FONT_SIZE);

function normalizeFontSize(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_FONT_SIZE;
  return Math.min(MAX_FONT_SIZE, Math.max(MIN_FONT_SIZE, Math.round(value)));
}

function applyFontSize(): void {
  if (typeof document === 'undefined') return;
  document.documentElement.style.setProperty('--app-font-size', `${fontSize}px`);
}

export function getFontSize(): number {
  return fontSize;
}

export function setFontSize(next: number): void {
  fontSize = normalizeFontSize(next);
  try {
    localStorage.setItem(STORAGE_KEY, String(fontSize));
  } catch {
    /* storage unavailable, choice just won't persist */
  }
  applyFontSize();
}

export function initFontSize(): void {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null && stored.trim()) fontSize = normalizeFontSize(Number(stored));
  } catch {
    /* storage unavailable */
  }
  applyFontSize();
}
