import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { RegionalBreakdown } from '@/types';
import { formatCount, formatWeightMetric } from '@/features/government/lib/analytics-display';

interface RegionalBreakdownTableProps {
  breakdown: RegionalBreakdown;
}

/**
 * Read-only regional breakdown as a table. Rendered as a table (not a map or
 * chart) because no map/chart library is bundled. Every value comes straight
 * from GET /analytics/regions; the component performs no aggregation.
 */
export function RegionalBreakdownTable({ breakdown }: RegionalBreakdownTableProps) {
  const { regions, weightUnit } = breakdown;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Region</TableHead>
          <TableHead>State</TableHead>
          <TableHead className="text-right">Submissions</TableHead>
          <TableHead className="text-right">Total weight</TableHead>
          <TableHead className="text-right">Recycled weight</TableHead>
          <TableHead className="text-right">Collectors</TableHead>
          <TableHead className="text-right">Recyclers</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {regions.map((row) => (
          <TableRow key={`${row.region}-${row.state ?? ''}`}>
            <TableCell className="font-medium">{row.region}</TableCell>
            <TableCell>{row.state ?? <span className="text-muted-foreground">—</span>}</TableCell>
            <TableCell className="text-right">{formatCount(row.totalSubmissions)}</TableCell>
            <TableCell className="text-right">
              {formatWeightMetric(row.totalWeight, weightUnit)}
            </TableCell>
            <TableCell className="text-right">
              {formatWeightMetric(row.recycledWeight, weightUnit)}
            </TableCell>
            <TableCell className="text-right">{formatCount(row.activeCollectors)}</TableCell>
            <TableCell className="text-right">{formatCount(row.activeRecyclers)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
