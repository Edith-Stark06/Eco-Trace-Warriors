import { Link } from 'react-router-dom';
import { StatusScreen } from '@/components/common/StatusScreen';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/routes';

interface NotFoundProps {
  fullScreen?: boolean;
}

/**
 * Reusable 404 screen for unmatched routes or missing resources. No business
 * logic.
 */
export function NotFound({ fullScreen }: NotFoundProps) {
  return (
    <StatusScreen
      code="404"
      title="Page not found"
      description="The page you are looking for doesn't exist or has been moved."
      fullScreen={fullScreen}
      action={
        <Button asChild>
          <Link to={ROUTES.dashboard}>Back to dashboard</Link>
        </Button>
      }
    />
  );
}
