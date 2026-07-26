import { Outlet } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { AccessDenied } from '@/components/common/AccessDenied';
import { roleHome } from '@/lib/routes';
import type { UserRole } from '@/types';

interface RoleGuardProps {
  /** Roles permitted to view the nested routes. */
  allow: UserRole[];
}

/**
 * Restricts nested routes to specific roles (UX-only; real authorization is
 * enforced server-side per docs/engineering/07_FRONTEND.md).
 *
 * Rendered inside a ProtectedRoute (and the MainLayout shell), so an
 * authenticated user is expected. States handled:
 * - loading      → spinner (session still resolving)
 * - authorized   → render nested routes
 * - unauthorized → the reusable AccessDenied screen with a link back to the
 *   user's role home, shown inside the shell so navigation stays available
 */
export function RoleGuard({ allow }: RoleGuardProps) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner fullScreen />;
  }

  if (!user || !allow.includes(user.role)) {
    return <AccessDenied homePath={roleHome(user?.role)} />;
  }

  return <Outlet />;
}
