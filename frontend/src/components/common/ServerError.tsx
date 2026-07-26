import { StatusScreen } from '@/components/common/StatusScreen';
import { Button } from '@/components/ui/button';

interface ServerErrorProps {
  /** Retry handler (e.g. reset an error boundary or refetch). */
  onRetry?: () => void;
  fullScreen?: boolean;
}

/**
 * Generic "something went wrong" screen for unexpected/server failures. Used as
 * the top-level ErrorBoundary fallback and available for feature-level error
 * states. No business logic.
 */
export function ServerError({ onRetry, fullScreen }: ServerErrorProps) {
  return (
    <StatusScreen
      code="500"
      title="Something went wrong"
      description="An unexpected error occurred. You can try again, and if the problem persists, reload the page."
      fullScreen={fullScreen}
      action={
        <>
          {onRetry && <Button onClick={onRetry}>Try again</Button>}
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </>
      }
    />
  );
}
