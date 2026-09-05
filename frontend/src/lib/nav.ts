import type { TranslationKey } from './i18n/en';

export const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', labelKey: 'nav.dashboard' satisfies TranslationKey },
  { href: '/tasks', label: 'Tasks', labelKey: 'nav.tasks' satisfies TranslationKey },
  { href: '/teams', label: 'Teams', labelKey: 'nav.teams' satisfies TranslationKey },
  { href: '/roles', label: 'Roles', labelKey: 'nav.roles' satisfies TranslationKey },
  {
    href: '/repositories',
    label: 'Repositories',
    labelKey: 'nav.repositories' satisfies TranslationKey
  },
  { href: '/agents', label: 'Workflow', labelKey: 'nav.workflow' satisfies TranslationKey },
  {
    href: '/integrations',
    label: 'Integrations',
    labelKey: 'nav.integrations' satisfies TranslationKey
  },
  { href: '/settings', label: 'Settings', labelKey: 'nav.settings' satisfies TranslationKey }
] as const;

export type NavItem = (typeof NAV_ITEMS)[number];

export function isActiveNavItem(pathname: string, href: string): boolean {
  return pathname === href || (href !== '/' && pathname.startsWith(`${href}/`));
}
