import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ROUTES } from '@/lib/routes';

/**
 * Guards routes that require authentication.
 *
 * While the auth state is resolving, a spinner is shown; unauthenticated
 * users are redirected to login with the attempted path preserved in
 * location state so they can be returned after signing in.
 *
 * Sprint 9.1: the auth provider currently reports `unauthenticated`, so this
 * guard is wired but effectively redirects until the login flow is built.
 */
export function ProtectedRoute() {
  const { status, isAuthenticated } = useAuth();
  const location = useLocation();

  if (status === 'idle' || status === 'loading') {
    return <LoadingSpinner fullScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to={ROUTES.login} state={{ from: location }} replace />;
  }

  return <Outlet />;
}
