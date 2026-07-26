import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { DemandForecast } from '@/types';
import {
  formatConfidence,
  formatCount,
  formatWeightMetric,
} from '@/features/government/lib/analytics-display';

interface ForecastTableProps {
  forecast: DemandForecast;
}

/**
 * Read-only AI demand forecast as a table (no chart library is bundled). Every
 * value is proxied from the AI service via GET /analytics/forecast and is
 * displayed as returned — no client-side modelling or interpolation.
 */
export function ForecastTable({ forecast }: ForecastTableProps) {
  const { points, weightUnit } = forecast;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Period</TableHead>
          <TableHead className="text-right">Predicted submissions</TableHead>
          <TableHead className="text-right">Predicted weight</TableHead>
          <TableHead className="text-right">Confidence</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {points.map((point) => (
          <TableRow key={point.period}>
            <TableCell className="font-medium whitespace-nowrap">{point.period}</TableCell>
            <TableCell className="text-right">{formatCount(point.predictedSubmissions)}</TableCell>
            <TableCell className="text-right">
              {formatWeightMetric(point.predictedWeight, weightUnit)}
            </TableCell>
            <TableCell className="text-right">{formatConfidence(point.confidence)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
