import { Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { roleHome } from '@/lib/routes';

/**
 * Generic authenticated landing route.
 *
 * Sprint 9.2 has no shared dashboard UI, so this simply forwards the user to
 * their role-specific home. Rendered inside ProtectedRoute, so a user exists.
 */
export function DashboardPage() {
  const { user } = useAuth();
  return <Navigate to={roleHome(user?.role)} replace />;
}
