import { EmptyState } from '@/components/dashboard/EmptyState';

/**
 * Dedicated informational state shown when the Government Analytics endpoints
 * respond with HTTP 404 — i.e. the backend Analytics module is not yet deployed
 * on this instance. This is an EXPECTED "feature unavailable" condition, not a
 * server error, so it is presented calmly and without a retry/alarm treatment.
 *
 * The surrounding dashboard is production-ready and will begin rendering live
 * analytics automatically once the backend Analytics module ships.
 */
export function AnalyticsUnavailable() {
  return (
    <EmptyState
      icon="government"
      title="Government Analytics are not yet available"
      description="The analytics service is not deployed on this backend instance yet. This dashboard will populate automatically once the Government Analytics module is live — no further setup is required here."
    />
  );
}
