import { Link } from 'react-router-dom';
import { StatusScreen } from '@/components/common/StatusScreen';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/routes';

interface AccessDeniedProps {
  /** Where the "Go to dashboard" action points (defaults to the dashboard). */
  homePath?: string;
  fullScreen?: boolean;
}

/**
 * Shown when an authenticated user reaches a route their role may not view.
 * Client-side gate is UX only; the server remains the authority. No business
 * logic.
 */
export function AccessDenied({ homePath = ROUTES.dashboard, fullScreen }: AccessDeniedProps) {
  return (
    <StatusScreen
      code="403"
      title="Access denied"
      description="You don't have permission to view this page. If you believe this is a mistake, contact your administrator."
      fullScreen={fullScreen}
      action={
        <Button asChild>
          <Link to={homePath}>Go to dashboard</Link>
        </Button>
      }
    />
  );
}
