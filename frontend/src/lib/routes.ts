/**
 * Application-wide route paths.
 *
 * Centralized so navigation and guards reference a single source of truth
 * instead of hardcoded string literals scattered across the app.
 */
import type { UserRole } from '@/types';
export const ROUTES = {
  root: '/',
  login: '/login',
  dashboard: '/dashboard',
  admin: '/admin',
  consumer: '/consumer',
  collector: '/collector',
  recycler: '/recycler',
  government: '/government',
  notFound: '*',
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

/**
 * Landing route for each role after login (docs/engineering/05_API.md roles).
 * Client-side convenience only — the server remains the authority on access.
 */
export const ROLE_HOME: Record<UserRole, string> = {
  ADMIN: ROUTES.admin,
  CONSUMER: ROUTES.consumer,
  COLLECTOR: ROUTES.collector,
  RECYCLER: ROUTES.recycler,
  GOVERNMENT: ROUTES.government,
};

/** Resolve the post-login home path for a role, falling back to the dashboard. */
export function roleHome(role: UserRole | undefined): string {
  return role ? (ROLE_HOME[role] ?? ROUTES.dashboard) : ROUTES.dashboard;
}
