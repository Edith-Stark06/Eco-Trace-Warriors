import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { ROUTES } from '@/lib/routes';
import type { UserRole } from '@/types';

interface RoleGuardProps {
  /** Roles permitted to view the nested routes. */
  allow: UserRole[];
  /** Where to send users whose role is not permitted. */
  redirectTo?: string;
}

/**
 * Restricts nested routes to specific roles (UX-only; real authorization is
 * enforced server-side per docs/engineering/07_FRONTEND.md).
 *
 * Assumes it is rendered inside a ProtectedRoute, so an authenticated user is
 * expected. If the user is missing or lacks an allowed role, they are
 * redirected to the shared dashboard.
 */
export function RoleGuard({ allow, redirectTo = ROUTES.dashboard }: RoleGuardProps) {
  const { user } = useAuth();

  if (!user || !allow.includes(user.role)) {
    return <Navigate to={redirectTo} replace />;
  }

  return <Outlet />;
}
