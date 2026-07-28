import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { Submission } from '@/types';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { formatDate, formatWeight, shortAddress } from '@/features/consumer/lib/submission-display';
import { IssueRewardDialog } from '@/features/admin/components/IssueRewardDialog';
import { AssignCollectorDialog } from '@/features/admin/components/AssignCollectorDialog';
import { AssignRecyclerDialog } from '@/features/admin/components/AssignRecyclerDialog';
import {
  isCollectorAssignable,
  isRecyclerAssignable,
  isRewardIssuable,
} from '@/features/admin/lib/admin-display';

interface AdminSubmissionsTableProps {
  submissions: readonly Submission[];
}

/**
 * Presentational table for the admin all-submissions view. Renders category,
 * status, weight, consumer id (userId), collector, recycler, and created date.
 * Offers the manual reward-issue action for eligible RECYCLED submissions.
 * Reuses shared display helpers — no duplicated formatting.
 */
export function AdminSubmissionsTable({ submissions }: AdminSubmissionsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Weight</TableHead>
          <TableHead>Address</TableHead>
          <TableHead>Created</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {submissions.map((submission) => (
          <TableRow key={submission.id}>
            <TableCell className="font-medium">{submission.category}</TableCell>
            <TableCell>
              <SubmissionStatusBadge status={submission.status} />
            </TableCell>
            <TableCell>{formatWeight(submission.estimatedWeight)}</TableCell>
            <TableCell className="max-w-[16rem] text-muted-foreground" title={submission.address}>
              {shortAddress(submission.address)}
            </TableCell>
            <TableCell className="whitespace-nowrap">{formatDate(submission.createdAt)}</TableCell>
            <TableCell>
              <div className="flex items-center justify-end gap-2">
                {isCollectorAssignable(submission.status) && (
                  <AssignCollectorDialog submission={submission} />
                )}
                {isRecyclerAssignable(submission.status) && (
                  <AssignRecyclerDialog submission={submission} />
                )}
                {isRewardIssuable(submission.status) && (
                  <IssueRewardDialog submission={submission} />
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
