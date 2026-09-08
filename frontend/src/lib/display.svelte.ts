export type DisplayMode = 'default' | 'jarvis';

const STORAGE_KEY = 'displayMode';

let mode = $state<DisplayMode>('default');

function applyDisplayMode(): void {
  if (typeof document === 'undefined') return;
  if (mode === 'jarvis') document.documentElement.dataset.display = 'jarvis';
  else delete document.documentElement.dataset.display;
}

export function getDisplayMode(): DisplayMode {
  return mode;
}

export function setDisplayMode(next: DisplayMode): void {
  mode = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable, choice just won't persist */
  }
  applyDisplayMode();
}

export function initDisplayMode(): void {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
  if (stored === 'jarvis' || stored === 'default') {
    mode = stored;
  }
  applyDisplayMode();
}
