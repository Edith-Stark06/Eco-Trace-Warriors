import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatWeight } from '@/features/consumer/lib/submission-display';
import type { CategoryBreakdownRow } from '@/features/recycler/lib/recycler-history-display';

interface CategoryBreakdownTableProps {
  categories: readonly CategoryBreakdownRow[];
}

/**
 * Real category breakdown of the recycler's completed jobs. Whatever
 * categories genuinely appear in the data are exactly what is shown — if
 * every job so far has been "Laptop", this table honestly shows one row.
 */
export function CategoryBreakdownTable({ categories }: CategoryBreakdownTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead className="text-right">Jobs</TableHead>
          <TableHead className="text-right">Estimated weight</TableHead>
          <TableHead className="text-right">Recovered weight</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {categories.map((row) => (
          <TableRow key={row.category}>
            <TableCell className="font-medium">{row.category}</TableCell>
            <TableCell className="text-right">{row.count}</TableCell>
            <TableCell className="text-right">{formatWeight(row.totalEstimatedWeight)}</TableCell>
            <TableCell className="text-right">{formatWeight(row.totalRecoveredWeight)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
