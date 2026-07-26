import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { roleHome } from '@/lib/routes';
import type { UserRole } from '@/types';

interface RoleGuardProps {
  /** Roles permitted to view the nested routes. */
  allow: UserRole[];
  /** Where to send users whose role is not permitted (defaults to their home). */
  redirectTo?: string;
}

/**
 * Restricts nested routes to specific roles (UX-only; real authorization is
 * enforced server-side per docs/engineering/07_FRONTEND.md).
 *
 * Rendered inside a ProtectedRoute, so an authenticated user is expected.
 * States handled:
 * - loading      → spinner (session still resolving)
 * - authorized   → render nested routes
 * - unauthorized → redirect to the user's role home (or `redirectTo`)
 */
export function RoleGuard({ allow, redirectTo }: RoleGuardProps) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner fullScreen />;
  }

  if (!user || !allow.includes(user.role)) {
    return <Navigate to={redirectTo ?? roleHome(user?.role)} replace />;
  }

  return <Outlet />;
}
