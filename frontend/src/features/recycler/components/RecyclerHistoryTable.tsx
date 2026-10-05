import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { RecyclerHistoryEntry } from '@/types';
import { formatDate, formatWeight } from '@/features/consumer/lib/submission-display';
import { formatMetric } from '@/features/consumer/lib/reward-display';
import { materialRecoveryEntries } from '@/features/recycler/lib/recycler-display';
import { recoveryRatePercent } from '@/features/recycler/lib/recycler-history-display';

interface RecyclerHistoryTableProps {
  jobs: readonly RecyclerHistoryEntry[];
}

const EMPTY = <span className="text-muted-foreground">—</span>;

/** Compact, comma-joined material list (e.g. "Copper 0.6 kg, Plastic 1.1 kg"), or "Not recorded". */
function materialRecoverySummaryText(value: unknown): string | null {
  const entries = materialRecoveryEntries(value);
  if (entries.length === 0) return null;
  return entries.map((entry) => `${entry.name} ${formatWeight(entry.weight)}`).join(', ');
}

/**
 * Per-job recycling history table. Every cell is a real, already-stored
 * value — recovery % is computed with the documented `recoveredWeight /
 * estimatedWeight * 100` formula and shown as "—" (never 0% or a guess) when
 * it cannot be honestly computed. `materialRecovery` shows "Not recorded"
 * rather than inferring a breakdown when the recycler never entered one.
 */
export function RecyclerHistoryTable({ jobs }: RecyclerHistoryTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Recycled</TableHead>
          <TableHead>Category</TableHead>
          <TableHead className="text-right">Estimated</TableHead>
          <TableHead className="text-right">Recovered</TableHead>
          <TableHead className="text-right">Recovery %</TableHead>
          <TableHead>Material recovery</TableHead>
          <TableHead className="text-right">CO₂ avoided</TableHead>
          <TableHead className="text-right">Energy saved</TableHead>
          <TableHead className="text-right">Landfill diverted</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => {
          const rate = recoveryRatePercent(job.estimatedWeight, job.recoveredWeight);
          const materials = materialRecoverySummaryText(job.materialRecovery);
          return (
            <TableRow key={job.id}>
              <TableCell className="whitespace-nowrap">
                {job.recycledAt ? formatDate(job.recycledAt) : EMPTY}
              </TableCell>
              <TableCell className="font-medium">{job.category}</TableCell>
              <TableCell className="text-right">{formatWeight(job.estimatedWeight)}</TableCell>
              <TableCell className="text-right">
                {job.recoveredWeight !== null ? formatWeight(job.recoveredWeight) : EMPTY}
              </TableCell>
              <TableCell className="text-right">
                {rate !== null ? `${rate.toFixed(1)}%` : EMPTY}
              </TableCell>
              <TableCell className="max-w-56 truncate" title={materials ?? undefined}>
                {materials ?? <span className="text-muted-foreground italic">Not recorded</span>}
              </TableCell>
              <TableCell className="text-right">
                {job.co2Saved !== null ? formatMetric(job.co2Saved, 'kg') : EMPTY}
              </TableCell>
              <TableCell className="text-right">
                {job.energySaved !== null ? formatMetric(job.energySaved, 'kWh') : EMPTY}
              </TableCell>
              <TableCell className="text-right">
                {job.landfillDiverted !== null ? formatMetric(job.landfillDiverted, 'kg') : EMPTY}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
