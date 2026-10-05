import { StatCard } from '@/components/dashboard/StatCard';
import { formatWeight } from '@/features/consumer/lib/submission-display';
import { formatMetric, formatPoints } from '@/features/consumer/lib/reward-display';
import type { RecyclerHistorySummary } from '@/features/recycler/lib/recycler-history-display';

interface RecyclerHistoryKpisProps {
  summary: RecyclerHistorySummary;
}

/**
 * Headline KPI band for the recycler's own history — every figure is a real
 * sum/average over this recycler's completed jobs only (never Government
 * Analytics' national totals). `averageRecoveryRate` is `null` when no job
 * has both a positive estimated weight and a recorded recovered weight; that
 * is shown honestly as "—", not a fabricated 0%.
 */
export function RecyclerHistoryKpis({ summary }: RecyclerHistoryKpisProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Total jobs recycled" value={formatPoints(summary.totalJobs)} icon="recycler" />
      <StatCard
        label="Total estimated weight"
        value={formatWeight(summary.totalEstimatedWeight)}
        icon="package"
      />
      <StatCard
        label="Total recovered weight"
        value={formatWeight(summary.totalRecoveredWeight)}
        icon="trendingUp"
      />
      <StatCard
        label="Average recovery rate"
        value={
          summary.averageRecoveryRate !== null ? `${summary.averageRecoveryRate.toFixed(1)}%` : '—'
        }
        icon="chart"
      />
      <StatCard label="CO₂ avoided" value={formatMetric(summary.totalCo2Saved, 'kg')} icon="brand" />
      <StatCard
        label="Energy saved"
        value={formatMetric(summary.totalEnergySaved, 'kWh')}
        icon="dashboard"
      />
      <StatCard
        label="Landfill diverted"
        value={formatMetric(summary.totalLandfillDiverted, 'kg')}
        icon="landfill"
      />
    </div>
  );
}
