import { StatCard } from '@/components/dashboard/StatCard';
import type { EnvironmentalImpact } from '@/types';
import { formatCount, formatWeightMetric } from '@/features/government/lib/analytics-display';

interface EnvironmentalImpactStatsProps {
  impact: EnvironmentalImpact;
}

/**
 * National environmental-impact metrics. Figures and units come directly from
 * GET /analytics/environmental-impact (mirroring the backend sustainability
 * shape); nothing is recomputed on the client. The trees-equivalent tile is
 * omitted when the backend does not supply it.
 */
export function EnvironmentalImpactStats({ impact }: EnvironmentalImpactStatsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="CO₂ saved"
        value={formatWeightMetric(impact.co2Saved, impact.co2Unit)}
        icon="brand"
      />
      <StatCard
        label="Energy saved"
        value={formatWeightMetric(impact.energySaved, impact.energyUnit)}
        icon="brand"
      />
      <StatCard
        label="Landfill diverted"
        value={formatWeightMetric(impact.landfillDiverted, impact.landfillUnit)}
        icon="recycler"
      />
      {impact.treesEquivalent !== null && (
        <StatCard
          label="Trees equivalent"
          value={formatCount(impact.treesEquivalent)}
          icon="brand"
          hint="Estimated"
        />
      )}
    </div>
  );
}
