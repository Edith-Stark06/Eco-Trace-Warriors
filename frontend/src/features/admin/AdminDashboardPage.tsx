import { useMemo, useState } from 'react';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { ServerError } from '@/components/common/ServerError';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { SUBMISSION_STATUSES } from '@/types';
import { AnalyticsUnavailable } from '@/features/government/components/AnalyticsUnavailable';
import { AdminUnavailable } from '@/features/admin/components/AdminUnavailable';
import { AdminSubmissionsTable } from '@/features/admin/components/AdminSubmissionsTable';
import { useAdminSubmissions } from '@/features/admin/hooks/use-admin';
import { sortByNewest, statusLabel } from '@/features/consumer/lib/submission-display';

/** Rows shown per page in the client-side pagination. */
const PAGE_SIZE = 10;
const ALL_STATUSES = 'ALL';

/**
 * Admin dashboard — system administration view.
 *
 * Sections backed by real APIs:
 *   - Submission Administration: GET /submissions (admin sees ALL via isAdmin→findAll)
 *   - Assignment: inline via Assign Collector/Recycler dialogs
 *       (GET /users?role=, PATCH /submissions/:id/assign, /assign-recycler)
 *   - Reward Administration: inline via IssueRewardDialog (POST /rewards/issue/:id)
 *
 * Sections with no backend API (informational unavailable state):
 *   - System Overview / Analytics: no /analytics router mounted
 *   - User Management: no user-listing endpoint exists
 *   - System Activity: no audit/activity feed endpoint exists
 *
 * Default export for React.lazy code-splitting.
 */
export default function AdminDashboardPage() {
  const { data, isPending, isError, refetch } = useAdminSubmissions();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>(ALL_STATUSES);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLowerCase();
    return sortByNewest(data).filter((s) => {
      const matchesStatus = status === ALL_STATUSES || s.status === status;
      const matchesSearch =
        query.length === 0 ||
        s.category.toLowerCase().includes(query) ||
        s.address.toLowerCase().includes(query);
      return matchesStatus && matchesSearch;
    });
  }, [data, search, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const resetPage = () => setPage(1);

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title="Admin Dashboard"
        description="System administration — manage submissions and issue rewards."
        actions={<Badge variant="secondary">Admin</Badge>}
      />

      {/* System Overview — no analytics API */}
      <Section
        title="System overview"
        description="National e-waste statistics and platform analytics."
      >
        <ContentCard>
          <AnalyticsUnavailable />
        </ContentCard>
      </Section>

      {/* User Management — role-scoped lookup exists, but no full user directory */}
      <Section title="User management" description="Platform user accounts and roles.">
        <AdminUnavailable description="Full user management is not yet available. The backend exposes only a role-scoped lookup (collectors and recyclers) used by the assignment workflow below — no complete user directory or account-editing endpoint exists." />
      </Section>

      {/* Submission Administration — GET /submissions (admin sees all) */}
      <Section
        title="Submission administration"
        description="All e-waste submissions across every user."
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="admin-submission-search">Search</Label>
            <Input
              id="admin-submission-search"
              type="search"
              placeholder="Search by category or address"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
            />
          </div>
          <div className="flex flex-col gap-2 sm:w-56">
            <Label htmlFor="admin-submission-status">Status</Label>
            <Select
              value={status}
              onValueChange={(value) => {
                setStatus(value);
                resetPage();
              }}
            >
              <SelectTrigger id="admin-submission-status">
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
            icon="admin"
            title={data && data.length > 0 ? 'No matching submissions' : 'No submissions yet'}
            description={
              data && data.length > 0
                ? 'Try adjusting your search or status filter.'
                : 'No submissions have been created on this platform yet.'
            }
          />
        ) : (
          <ContentCard>
            <AdminSubmissionsTable submissions={pageItems} />
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
                  aria-label="Previous page"
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
                  aria-label="Next page"
                >
                  Next
                </Button>
              </div>
            </div>
          </ContentCard>
        )}
      </Section>

      {/* Assignment Management — inline in the submissions table */}
      <Section
        title="Assignment management"
        description="Assign collectors and recyclers to submissions."
      >
        <ContentCard>
          <p className="text-sm text-muted-foreground">
            Assignments are made inline in the Submission Administration table above. Use{' '}
            <strong>Assign Collector</strong> on a <strong>Pending</strong> submission, and{' '}
            <strong>Assign Recycler</strong> once it is <strong>Collected</strong>. Eligible
            partners are loaded from the backend directory; the assignment is validated server-side.
          </p>
        </ContentCard>
      </Section>

      {/* Reward Administration — note: IssueRewardDialog is inline in the submissions table */}
      <Section
        title="Reward administration"
        description="Manual reward issuance for RECYCLED submissions."
      >
        <ContentCard>
          <p className="text-sm text-muted-foreground">
            Manual reward issuance is available inline in the Submission Administration table above.
            Select any submission with status <strong>Recycled</strong> and use the{' '}
            <strong>Issue Reward</strong> action. Rewards are calculated entirely by the backend —
            no values are computed here.
          </p>
        </ContentCard>
      </Section>

      {/* System Activity — no audit/activity feed API */}
      <Section title="System activity" description="Platform-wide audit trail and recent events.">
        <AdminUnavailable description="System activity feed is not yet available. No audit or activity endpoint exists on this backend instance." />
      </Section>
    </div>
  );
}
