import { en, type TranslationKey } from './en';
import { ka } from './ka';

export type Locale = 'en' | 'ka';

const dictionaries: Record<Locale, Record<TranslationKey, string>> = { en, ka };
const STORAGE_KEY = 'locale';

let locale = $state<Locale>('en');

export function getLocale(): Locale {
  return locale;
}

export function setLocale(next: Locale): void {
  locale = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable, choice just won't persist */
  }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = next;
  }
}

export function initLocale(): void {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
  if (stored === 'en' || stored === 'ka') {
    setLocale(stored);
    return;
  }
  const browserLocale = typeof navigator !== 'undefined' ? navigator.language : 'en';
  setLocale(browserLocale.toLowerCase().startsWith('ka') ? 'ka' : 'en');
}

export function t(key: TranslationKey, params?: Record<string, string | number>): string {
  const template = dictionaries[locale][key] ?? dictionaries.en[key] ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, token: string) =>
    token in params ? String(params[token]) : match
  );
}
