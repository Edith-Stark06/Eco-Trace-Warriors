import { Link } from 'react-router-dom';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { recyclerAssignmentPath } from '@/lib/routes';
import type { CompleteRecyclingResult, Submission } from '@/types';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { formatDate, formatWeight } from '@/features/consumer/lib/submission-display';
import { RecyclerActionButton } from '@/features/recycler/components/RecyclerActionButton';
import { isReadOnlyForRecycler, RECYCLED_LABEL } from '@/features/recycler/lib/recycler-display';

interface RecyclerAssignmentsTableProps {
  assignments: readonly Submission[];
  /** Receives the backend `{ submission, reward }` result after completion. */
  onCompleted?: (result: CompleteRecyclingResult) => void;
}

/**
 * Presentational table for a recycler's assignments. Renders category, weight,
 * the collector completion date (`completedAt`), status, and the single legal
 * workflow action per row (or a read-only "Completed" note once RECYCLED).
 * Reuses the shared submission badge and pure display helpers — no duplicated
 * formatting.
 */
export function RecyclerAssignmentsTable({
  assignments,
  onCompleted,
}: RecyclerAssignmentsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead>Weight</TableHead>
          <TableHead>Collected</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {assignments.map((assignment) => (
          <TableRow key={assignment.id}>
            <TableCell className="font-medium">{assignment.category}</TableCell>
            <TableCell>{formatWeight(assignment.estimatedWeight)}</TableCell>
            <TableCell className="whitespace-nowrap">
              {assignment.completedAt ? (
                formatDate(assignment.completedAt)
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell>
              <SubmissionStatusBadge status={assignment.status} />
            </TableCell>
            <TableCell>
              <div className="flex items-center justify-end gap-2">
                <Button asChild variant="ghost" size="sm">
                  <Link to={recyclerAssignmentPath(assignment.id)}>View</Link>
                </Button>
                {isReadOnlyForRecycler(assignment.status) ? (
                  <span className="text-xs text-muted-foreground">{RECYCLED_LABEL}</span>
                ) : (
                  <RecyclerActionButton submission={assignment} onCompleted={onCompleted} />
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
