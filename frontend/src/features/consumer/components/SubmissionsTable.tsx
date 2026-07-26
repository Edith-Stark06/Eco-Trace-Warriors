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
import { consumerSubmissionPath } from '@/lib/routes';
import type { Submission } from '@/types';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { EditSubmissionDialog } from '@/features/consumer/components/EditSubmissionDialog';
import { DeleteSubmissionDialog } from '@/features/consumer/components/DeleteSubmissionDialog';
import {
  formatDate,
  formatWeight,
  isSubmissionMutable,
  shortAddress,
} from '@/features/consumer/lib/submission-display';

interface SubmissionsTableProps {
  submissions: readonly Submission[];
  /** Show the per-row actions column (View / Edit / Delete). Default true. */
  showActions?: boolean;
}

/**
 * Presentational table for a list of submissions. Renders category, status,
 * weight, created date, and address, plus optional row actions. Edit and Delete
 * are offered only for PENDING submissions — mirroring the backend rule so the
 * user is never shown an action the server would reject.
 */
export function SubmissionsTable({ submissions, showActions = true }: SubmissionsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Weight</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Address</TableHead>
          {showActions && <TableHead className="text-right">Actions</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {submissions.map((submission) => {
          const mutable = isSubmissionMutable(submission.status);
          return (
            <TableRow key={submission.id}>
              <TableCell className="font-medium">{submission.category}</TableCell>
              <TableCell>
                <SubmissionStatusBadge status={submission.status} />
              </TableCell>
              <TableCell>{formatWeight(submission.estimatedWeight)}</TableCell>
              <TableCell className="whitespace-nowrap">
                {formatDate(submission.createdAt)}
              </TableCell>
              <TableCell className="max-w-[16rem] text-muted-foreground" title={submission.address}>
                {shortAddress(submission.address)}
              </TableCell>
              {showActions && (
                <TableCell>
                  <div className="flex items-center justify-end gap-2">
                    <Button asChild variant="ghost" size="sm">
                      <Link to={consumerSubmissionPath(submission.id)}>View</Link>
                    </Button>
                    {mutable && (
                      <>
                        <EditSubmissionDialog
                          submission={submission}
                          trigger={
                            <Button variant="outline" size="sm">
                              Edit
                            </Button>
                          }
                        />
                        <DeleteSubmissionDialog
                          submission={submission}
                          trigger={
                            <Button variant="ghost" size="sm">
                              Delete
                            </Button>
                          }
                        />
                      </>
                    )}
                  </div>
                </TableCell>
              )}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
