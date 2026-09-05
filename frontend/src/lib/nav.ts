export const NAV_ITEMS = [
  { href: '/', label: 'Dashboard' },
  { href: '/tasks', label: 'Tasks' },
  { href: '/repositories', label: 'Repositories' },
  { href: '/agents', label: 'Workflow' },
  { href: '/integrations', label: 'Integrations' },
  { href: '/settings', label: 'Settings' }
] as const;

export type NavItem = (typeof NAV_ITEMS)[number];

export function isActiveNavItem(pathname: string, href: string): boolean {
  return pathname === href || (href !== '/' && pathname.startsWith(`${href}/`));
}
