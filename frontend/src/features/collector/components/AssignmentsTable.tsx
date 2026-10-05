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
import { collectorAssignmentPath } from '@/lib/routes';
import type { Submission } from '@/types';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { formatDate, formatWeight, shortAddress } from '@/features/consumer/lib/submission-display';
import { AssignmentActionButton } from '@/features/collector/components/AssignmentActionButton';
import { AWAITING_RECYCLER_MESSAGE } from '@/features/collector/lib/assignment-display';

interface AssignmentsTableProps {
  assignments: readonly Submission[];
}

/**
 * Presentational table for a collector's assignments. Renders category,
 * address, estimated weight, status, and assigned date, plus the single legal
 * workflow action per row (or a read-only note once COLLECTED). Reuses the
 * shared submission badge and pure display helpers — no duplicated formatting.
 */
export function AssignmentsTable({ assignments }: AssignmentsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead>Address</TableHead>
          <TableHead>Weight</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Assigned</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {assignments.map((assignment) => (
          <TableRow key={assignment.id}>
            <TableCell className="font-medium">{assignment.category}</TableCell>
            <TableCell className="max-w-[16rem] text-muted-foreground" title={assignment.address}>
              {shortAddress(assignment.address)}
            </TableCell>
            <TableCell>{formatWeight(assignment.estimatedWeight)}</TableCell>
            <TableCell>
              <SubmissionStatusBadge status={assignment.status} />
            </TableCell>
            <TableCell className="whitespace-nowrap">{formatDate(assignment.createdAt)}</TableCell>
            <TableCell>
              <div className="flex items-center justify-end gap-2">
                <Button asChild variant="ghost" size="sm">
                  <Link to={collectorAssignmentPath(assignment.id)}>View</Link>
                </Button>
                {assignment.status === 'COLLECTED' ? (
                  <span className="text-xs text-muted-foreground">{AWAITING_RECYCLER_MESSAGE}</span>
                ) : (
                  <AssignmentActionButton submission={assignment} />
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
