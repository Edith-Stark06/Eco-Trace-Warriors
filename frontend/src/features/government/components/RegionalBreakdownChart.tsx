import { StatCard } from '@/components/dashboard/StatCard';
import { HorizontalBarChart } from '@/components/charts/HorizontalBarChart';
import type { RegionalBreakdown } from '@/types';
import { formatCount, formatWeightMetric } from '@/features/government/lib/analytics-display';

interface RegionalBreakdownChartProps {
  breakdown: RegionalBreakdown;
}

/**
 * Ranked regional visualization for GET /analytics/regions. No geographic
 * map is rendered — the backend never returns per-region coordinates
 * (`RegionalStat.latitude`/`longitude` are always `null`, see
 * frontend/src/types/analytics.ts), so a map would have to fabricate
 * placement; a ranked bar chart uses exactly the real data the endpoint
 * provides. The three summary tiles are plain aggregations (count, max, sum)
 * over the same real per-region rows already returned by the endpoint — not
 * new data, not an estimate.
 */
export function RegionalBreakdownChart({ breakdown }: RegionalBreakdownChartProps) {
  const { regions, weightUnit } = breakdown;

  const topRegion = regions.reduce((top, row) =>
    row.recycledWeight > top.recycledWeight ? row : top,
  );
  const totalFieldWorkforce = regions.reduce(
    (sum, row) => sum + row.activeCollectors + row.activeRecyclers,
    0,
  );

  const rankedByRecycledWeight = [...regions]
    .sort((a, b) => b.recycledWeight - a.recycledWeight)
    .slice(0, 10)
    .map((row) => ({
      key: row.region,
      label: row.region,
      value: row.recycledWeight,
      formattedValue: formatWeightMetric(row.recycledWeight, weightUnit),
    }));

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Regions reporting" value={formatCount(regions.length)} icon="region" />
        <StatCard
          label="Top region by recycled weight"
          value={topRegion.region}
          icon="trendingUp"
          hint={formatWeightMetric(topRegion.recycledWeight, weightUnit)}
        />
        <StatCard
          label="Active field workforce"
          value={formatCount(totalFieldWorkforce)}
          icon="users"
          hint="Collectors + recyclers, all regions"
        />
      </div>
      <HorizontalBarChart
        ariaLabel="Regions ranked by recycled weight"
        items={rankedByRecycledWeight}
      />
    </div>
  );
}
