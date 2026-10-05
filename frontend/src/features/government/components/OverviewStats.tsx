import { StatCard } from '@/components/dashboard/StatCard';
import type { NationalOverview } from '@/types';
import { formatCount, formatWeightMetric } from '@/features/government/lib/analytics-display';

interface OverviewStatsProps {
  overview: NationalOverview;
}

/**
 * National statistics summary row. Presentation only — every figure comes
 * straight from GET /analytics/overview and is formatted, never computed.
 */
export function OverviewStats({ overview }: OverviewStatsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Total submissions"
        value={formatCount(overview.totalSubmissions)}
        icon="package"
        hint="Nationwide"
      />
      <StatCard
        label="Recycled"
        value={formatCount(overview.recycledSubmissions)}
        icon="recycler"
        hint="Reached RECYCLED"
      />
      <StatCard
        label="Recovered weight"
        value={formatWeightMetric(overview.totalRecoveredWeight, overview.weightUnit)}
        icon="brand"
        hint="Material recovered"
      />
      <StatCard
        label="Rewards issued"
        value={formatCount(overview.totalRewardsIssued)}
        icon="coins"
        hint="Green coins awarded"
      />
    </div>
  );
}
