import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LoadingSpinnerProps {
  className?: string;
  label?: string;
  /** Center within the full viewport height (useful for route fallbacks). */
  fullScreen?: boolean;
}

/** Reusable loading indicator with an accessible label. */
export function LoadingSpinner({ className, label = 'Loading…', fullScreen }: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex flex-col items-center justify-center gap-3 text-muted-foreground',
        fullScreen && 'min-h-screen',
        className,
      )}
    >
      <Loader2 className="size-6 animate-spin" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
