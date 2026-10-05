import { EmptyState } from '@/components/dashboard/EmptyState';

/**
 * Informational state shown when an Admin section has no backing backend API.
 * Presented calmly — this is an expected "feature not yet available" condition,
 * not a server error. The section will populate automatically once the relevant
 * backend module ships.
 */
export function AdminUnavailable({ description }: { description: string }) {
  return <EmptyState icon="admin" title="Not yet available" description={description} />;
}
