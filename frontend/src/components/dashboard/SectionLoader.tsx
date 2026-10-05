import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface SectionLoaderProps {
  /** Number of skeleton lines to render. */
  lines?: number;
  className?: string;
}

/**
 * Inline loading placeholder for a single section or panel of a page, when the
 * surrounding shell is already rendered.
 */
export function SectionLoader({ lines = 3, className }: SectionLoaderProps) {
  return (
    <div
      className={cn('flex flex-col gap-3', className)}
      role="status"
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">Loading…</span>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} className={cn('h-4', index === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  );
}
