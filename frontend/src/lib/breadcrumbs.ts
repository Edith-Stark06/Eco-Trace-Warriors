/**
 * Breadcrumb derivation.
 *
 * Breadcrumbs are generated automatically from the current pathname rather than
 * declared per page. Every trail is rooted at Dashboard; each remaining path
 * segment becomes a crumb whose label is looked up (falling back to a
 * title-cased segment) so new routes need no extra wiring.
 */
import { ROUTES } from '@/lib/routes';

export interface Breadcrumb {
  label: string;
  /** Target path, or undefined for the current (non-navigable) page. */
  path?: string;
}

/** Human-readable labels for known path segments. */
const SEGMENT_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  consumer: 'Consumer',
  collector: 'Collector',
  recycler: 'Recycler',
  government: 'Government',
  admin: 'Admin',
  settings: 'Settings',
};

/** Title-case an unknown segment (e.g. "audit-log" → "Audit Log"). */
function labelForSegment(segment: string): string {
  return (
    SEGMENT_LABELS[segment] ??
    segment
      .split('-')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  );
}

/**
 * Build the breadcrumb trail for a pathname. Always starts at Dashboard; the
 * final crumb is the current page and carries no link.
 */
export function buildBreadcrumbs(pathname: string): Breadcrumb[] {
  const segments = pathname.split('/').filter(Boolean);
  const trail: Breadcrumb[] = [{ label: 'Dashboard', path: ROUTES.dashboard }];

  let accumulated = '';
  for (const segment of segments) {
    accumulated += `/${segment}`;
    if (segment === 'dashboard') continue; // already the root crumb
    trail.push({ label: labelForSegment(segment), path: accumulated });
  }

  // The last crumb represents the current page — drop its link.
  const last = trail[trail.length - 1];
  return trail.map((crumb, index) => (index === trail.length - 1 ? { label: last.label } : crumb));
}
