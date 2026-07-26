import { StatCard } from '@/components/dashboard/StatCard';
import { formatWeight } from '@/features/consumer/lib/submission-display';
import type { RecyclerStatusSummary as RecyclerStatusSummaryData } from '@/features/recycler/lib/recycler-display';

interface RecyclerStatusSummaryProps {
  summary: RecyclerStatusSummaryData;
}

/**
 * Status summary row for the recycler dashboard: Collected (awaiting start),
 * Recycling (in progress), Completed Today, and Recovered Weight. All counts are
 * computed from the assignment list (no extra API call) and rendered with the
 * shared StatCard.
 */
export function RecyclerStatusSummary({ summary }: RecyclerStatusSummaryProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Collected" value={String(summary.collected)} icon="package" />
      <StatCard label="Recycling" value={String(summary.recycling)} icon="recycler" />
      <StatCard label="Completed Today" value={String(summary.completedToday)} icon="check" />
      <StatCard
        label="Recovered Weight"
        value={formatWeight(summary.recoveredWeight)}
        icon="coins"
      />
    </div>
  );
}
