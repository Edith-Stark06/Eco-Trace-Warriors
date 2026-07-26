import { StatCard } from '@/components/dashboard/StatCard';
import type { StatusSummary as StatusSummaryData } from '@/features/collector/lib/assignment-display';

interface StatusSummaryProps {
  summary: StatusSummaryData;
}

/**
 * Status summary row for the collector dashboard: Assigned, Accepted, In
 * Progress, and Collected Today. All counts are computed from the assignment
 * list (no extra API call) and rendered with the shared StatCard.
 */
export function StatusSummary({ summary }: StatusSummaryProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Assigned" value={String(summary.assigned)} icon="package" />
      <StatCard label="Accepted" value={String(summary.accepted)} icon="check" />
      <StatCard label="In Progress" value={String(summary.inProgress)} icon="collector" />
      <StatCard label="Collected Today" value={String(summary.collectedToday)} icon="recycler" />
    </div>
  );
}
