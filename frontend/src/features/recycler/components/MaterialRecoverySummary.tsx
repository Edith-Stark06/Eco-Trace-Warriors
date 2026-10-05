import { EmptyState } from '@/components/dashboard/EmptyState';
import { formatWeight } from '@/features/consumer/lib/submission-display';
import type { MaterialSummary } from '@/features/recycler/lib/recycler-history-display';

interface MaterialRecoverySummaryProps {
  summary: MaterialSummary;
}

/**
 * Aggregated real material-recovery breakdown across the recycler's history.
 * Only ever totals materials the recycler actually recorded at completion
 * time — never a percentage, never inferred from device category. The
 * "recorded for X of Y" line is shown deliberately prominently because this
 * data is genuinely partial (materialRecovery is an optional field).
 */
export function MaterialRecoverySummary({ summary }: MaterialRecoverySummaryProps) {
  if (summary.materials.length === 0) {
    return (
      <EmptyState
        icon="package"
        title="No material recovery recorded yet"
        description="Record materials when completing a recycling job to see a breakdown here."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {summary.materials.map((material) => (
          <li key={material.name} className="flex items-center justify-between gap-4 text-sm">
            <span className="font-medium">{material.name}</span>
            <span className="text-muted-foreground">{formatWeight(material.totalWeight)}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Material data recorded for {summary.jobsWithMaterialData} of {summary.totalJobs} completed
        jobs.
      </p>
    </div>
  );
}
