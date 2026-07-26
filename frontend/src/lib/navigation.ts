/**
 * Sidebar navigation model.
 *
 * A single declarative list drives both the desktop sidebar and the mobile
 * drawer. Each item names an icon in the central registry (`@/lib/icons`) and,
 * optionally, the roles allowed to see it — items with no `roles` are visible
 * to every authenticated user. Role filtering here is UX-only; real
 * authorization is enforced server-side (see RoleGuard).
 */
import { ROUTES } from '@/lib/routes';
import type { IconName } from '@/lib/icons';
import type { UserRole } from '@/types';

export interface NavItem {
  label: string;
  path: string;
  icon: IconName;
  /** Roles permitted to see this item. Omit to show it to everyone. */
  roles?: UserRole[];
}

/**
 * Primary navigation. Role-specific dashboards are gated to their role; the
 * generic Dashboard, Settings entries are shared.
 */
export const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', path: ROUTES.dashboard, icon: 'dashboard' },
  { label: 'Submissions', path: ROUTES.consumerSubmissions, icon: 'package', roles: ['CONSUMER'] },
  { label: 'Rewards', path: ROUTES.consumerRewards, icon: 'coins', roles: ['CONSUMER'] },
  { label: 'Collector', path: ROUTES.collector, icon: 'collector', roles: ['COLLECTOR'] },
  { label: 'Recycler', path: ROUTES.recycler, icon: 'recycler', roles: ['RECYCLER'] },
  {
    label: 'Government',
    path: ROUTES.government,
    icon: 'government',
    roles: ['GOVERNMENT', 'ADMIN'],
  },
  { label: 'Admin', path: ROUTES.admin, icon: 'admin', roles: ['ADMIN'] },
  { label: 'Settings', path: ROUTES.settings, icon: 'settings' },
];

/** Nav items visible to the given role (undefined role → shared items only). */
export function navItemsForRole(role: UserRole | undefined): NavItem[] {
  return NAV_ITEMS.filter(
    (item) => !item.roles || (role !== undefined && item.roles.includes(role)),
  );
}
