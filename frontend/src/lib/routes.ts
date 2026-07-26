/**
 * Application-wide route paths.
 *
 * Centralized so navigation and guards reference a single source of truth
 * instead of hardcoded string literals scattered across the app.
 */
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
