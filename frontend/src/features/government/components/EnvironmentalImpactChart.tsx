import { HorizontalBarChart } from '@/components/charts/HorizontalBarChart';
import type { EnvironmentalImpact } from '@/types';
import { formatWeightMetric } from '@/features/government/lib/analytics-display';

interface EnvironmentalImpactChartProps {
  impact: EnvironmentalImpact;
}

/**
 * Compact relative-scale comparison of the three real environmental-impact
 * figures. Bar length is purely a visual "which is largest" cue — CO₂ (kg),
 * energy (kWh), and landfill diversion (kg) are different units, so each
 * bar's real value and unit is always printed as text rather than implying
 * the units are equivalent. No value here is computed beyond formatting;
 * every number comes from GET /analytics/environmental-impact as-is.
 */
export function EnvironmentalImpactChart({ impact }: EnvironmentalImpactChartProps) {
  return (
    <HorizontalBarChart
      ariaLabel="Relative comparison of CO2 avoided, energy saved, and landfill diverted"
      items={[
        {
          key: 'co2',
          label: 'CO₂ avoided',
          value: impact.co2Saved,
          formattedValue: formatWeightMetric(impact.co2Saved, impact.co2Unit),
        },
        {
          key: 'energy',
          label: 'Energy saved',
          value: impact.energySaved,
          formattedValue: formatWeightMetric(impact.energySaved, impact.energyUnit),
        },
        {
          key: 'landfill',
          label: 'Landfill diverted',
          value: impact.landfillDiverted,
          formattedValue: formatWeightMetric(impact.landfillDiverted, impact.landfillUnit),
        },
      ]}
    />
  );
}
