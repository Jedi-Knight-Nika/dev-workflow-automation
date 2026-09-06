import type { TranslationKey } from './i18n/en';

export const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', group: '', labelKey: 'nav.dashboard' satisfies TranslationKey },
  { href: '/tasks', label: 'Tasks', group: '', labelKey: 'nav.tasks' satisfies TranslationKey },
  {
    href: '/teams',
    label: 'Teams',
    group: 'Workforce',
    labelKey: 'nav.teams' satisfies TranslationKey
  },
  {
    href: '/agents',
    label: 'Workflow',
    group: 'Workforce',
    labelKey: 'nav.workflow' satisfies TranslationKey
  },
  {
    href: '/roles',
    label: 'Roles',
    group: 'Workforce',
    labelKey: 'nav.roles' satisfies TranslationKey
  },
  {
    href: '/repositories',
    label: 'Repositories',
    group: 'Resources',
    labelKey: 'nav.repositories' satisfies TranslationKey
  },
  {
    href: '/integrations',
    label: 'Integrations',
    group: 'Resources',
    labelKey: 'nav.integrations' satisfies TranslationKey
  },
  {
    href: '/settings',
    label: 'Settings',
    group: 'System',
    labelKey: 'nav.settings' satisfies TranslationKey
  }
] as const;

export type NavItem = (typeof NAV_ITEMS)[number];

export function isActiveNavItem(pathname: string, href: string): boolean {
  return pathname === href || (href !== '/' && pathname.startsWith(`${href}/`));
}
