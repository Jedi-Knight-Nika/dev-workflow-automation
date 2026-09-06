export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

let theme = $state<Theme>('dark');

export function getTheme(): Theme {
  return theme;
}

export function setTheme(next: Theme): void {
  theme = next;
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = next;
  }
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable, theme just won't persist */
  }
}

export function initTheme(): void {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
  if (stored === 'light' || stored === 'dark') {
    theme = stored;
    return;
  }
  const prefersLight =
    typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches;
  theme = prefersLight ? 'light' : 'dark';
  // No stored choice yet: the no-FOUC inline script in app.html only acts on a
  // stored value, so the system-preference fallback here must also update the
  // DOM attribute itself, or the toggle icon and the rendered theme disagree.
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme;
  }
}
