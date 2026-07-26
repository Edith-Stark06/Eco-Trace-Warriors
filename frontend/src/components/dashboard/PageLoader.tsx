import { Skeleton } from '@/components/ui/skeleton';

/**
 * Full-page loading placeholder used as the Suspense fallback for lazy-loaded
 * dashboard pages. Mirrors the typical page shape (header + stat row + panel)
 * so the transition to real content is visually stable.
 */
export function PageLoader() {
  return (
    <div className="flex flex-col gap-6" role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading page…</span>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-24 w-full" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
