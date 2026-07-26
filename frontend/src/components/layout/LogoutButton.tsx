import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { icons } from '@/lib/icons';
import { useAuth } from '@/hooks/use-auth';
import { ROUTES } from '@/lib/routes';
import { cn } from '@/lib/utils';

interface LogoutButtonProps {
  className?: string;
  /** Called after logout completes (used to close the mobile drawer). */
  onAfterLogout?: () => void;
}

/**
 * Reusable sign-out control. Logout is best-effort server-side; the local
 * session is always cleared and the user is returned to the login page. Shared
 * by the sidebar and the mobile drawer so the flow lives in exactly one place.
 */
export function LogoutButton({ className, onAfterLogout }: LogoutButtonProps) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const LogOutIcon = icons.logout;

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      toast.success('Signed out.');
      onAfterLogout?.();
      navigate(ROUTES.login, { replace: true });
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <Button
      variant="ghost"
      onClick={handleLogout}
      disabled={isLoggingOut}
      className={cn('gap-3 text-muted-foreground', className)}
    >
      <LogOutIcon className="size-4 shrink-0" aria-hidden="true" />
      <span>Logout</span>
    </Button>
  );
}
