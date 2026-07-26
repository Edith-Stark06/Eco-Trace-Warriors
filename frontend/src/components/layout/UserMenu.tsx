import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/use-auth';
import { ROUTES } from '@/lib/routes';

/**
 * Compact authenticated-user control for the navbar: shows the signed-in
 * identity and a sign-out action. Logout is best-effort server-side; the local
 * session is always cleared and the user is sent to the login page.
 */
export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  if (!user) return null;

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      toast.success('Signed out.');
      navigate(ROUTES.login, { replace: true });
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <div className="hidden flex-col text-right leading-tight sm:flex">
        <span className="text-sm font-medium">{user.fullName}</span>
        <span className="text-xs text-muted-foreground">{user.role}</span>
      </div>
      <Button
        variant="ghost"
        size="icon"
        onClick={handleLogout}
        disabled={isLoggingOut}
        aria-label="Sign out"
        title="Sign out"
      >
        <LogOut aria-hidden="true" />
      </Button>
    </div>
  );
}
