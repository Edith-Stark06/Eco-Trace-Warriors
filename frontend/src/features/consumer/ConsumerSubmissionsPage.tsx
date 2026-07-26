import { useMemo, useState } from 'react';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { ServerError } from '@/components/common/ServerError';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { SUBMISSION_STATUSES } from '@/types';
import { useSubmissions } from '@/features/consumer/hooks/use-submissions';
import { SubmissionsTable } from '@/features/consumer/components/SubmissionsTable';
import { CreateSubmissionDialog } from '@/features/consumer/components/CreateSubmissionDialog';
import { sortByNewest, statusLabel } from '@/features/consumer/lib/submission-display';

/** Rows shown per page in the client-side pagination. */
const PAGE_SIZE = 10;

const ALL_STATUSES = 'ALL';

/**
 * Full submissions list with client-side search, status filter, and
 * pagination. Data is fetched once via React Query and filtered/paged in
 * memory (the list is a single user's own submissions, so this is cheap and
 * avoids extra round-trips).
 */
export default function ConsumerSubmissionsPage() {
  const { data, isPending, isError, refetch } = useSubmissions();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>(ALL_STATUSES);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLowerCase();
    return sortByNewest(data).filter((submission) => {
      const matchesStatus = status === ALL_STATUSES || submission.status === status;
      const matchesSearch =
        query.length === 0 ||
        submission.category.toLowerCase().includes(query) ||
        submission.address.toLowerCase().includes(query);
      return matchesStatus && matchesSearch;
    });
  }, [data, search, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // Reset to the first page whenever the filters change the result set.
  const resetPage = () => setPage(1);

  return (
    <div className="flex flex-col gap-6">
      <DashboardHeader
        title="Submissions"
        description="View and manage all of your e-waste submissions."
        actions={<CreateSubmissionDialog />}
      />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-2">
          <Label htmlFor="submission-search">Search</Label>
          <Input
            id="submission-search"
            type="search"
            placeholder="Search by category or address"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              resetPage();
            }}
          />
        </div>
        <div className="flex flex-col gap-2 sm:w-56">
          <Label htmlFor="submission-status">Status</Label>
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value);
              resetPage();
            }}
          >
            <SelectTrigger id="submission-status">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_STATUSES}>All statuses</SelectItem>
              {SUBMISSION_STATUSES.map((value) => (
                <SelectItem key={value} value={value}>
                  {statusLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {isPending ? (
        <SkeletonTable rows={8} columns={6} />
      ) : isError ? (
        <ServerError onRetry={() => void refetch()} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="package"
          title={data && data.length > 0 ? 'No matching submissions' : 'No submissions yet'}
          description={
            data && data.length > 0
              ? 'Try adjusting your search or status filter.'
              : 'Create your first e-waste submission to get started.'
          }
          action={data && data.length > 0 ? undefined : <CreateSubmissionDialog />}
        />
      ) : (
        <ContentCard>
          <SubmissionsTable submissions={pageItems} />
          <div className="mt-4 flex flex-col items-center justify-between gap-3 sm:flex-row">
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Showing {pageItems.length} of {filtered.length} submissions
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={currentPage <= 1}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={currentPage >= totalPages}
              >
                Next
              </Button>
            </div>
          </div>
        </ContentCard>
      )}
    </div>
  );
}
