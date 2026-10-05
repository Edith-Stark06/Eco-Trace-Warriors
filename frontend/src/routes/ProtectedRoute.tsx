import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ROUTES } from '@/lib/routes';

/**
 * Guards routes that require authentication.
 *
 * States handled:
 * - loading        → full-screen spinner while the session bootstraps
 * - authenticated  → render the nested routes
 * - unauthenticated → redirect to login, preserving the attempted path so the
 *   user can be returned after signing in
 */
export function ProtectedRoute() {
  const { isLoading, isAuthenticated } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingSpinner fullScreen label="Restoring your session…" />;
  }

  if (!isAuthenticated) {
    return <Navigate to={ROUTES.login} state={{ from: location }} replace />;
  }

  return <Outlet />;
}
