import { Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { LoginForm } from '@/features/auth/LoginForm';
import { roleHome } from '@/lib/routes';

/**
 * Login route.
 *
 * If a session is still resolving, shows a spinner; if the user is already
 * authenticated, redirects to their role home; otherwise renders the form.
 */
export function LoginPage() {
  const { isLoading, isAuthenticated, user } = useAuth();

  if (isLoading) {
    return <LoadingSpinner label="Loading…" />;
  }

  if (isAuthenticated) {
    return <Navigate to={roleHome(user?.role)} replace />;
  }

  return <LoginForm />;
}
