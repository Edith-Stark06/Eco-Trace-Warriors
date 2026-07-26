import { useNavigate, useParams } from 'react-router-dom';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { PageLoader } from '@/components/dashboard/PageLoader';
import { NotFound } from '@/components/common/NotFound';
import { ServerError } from '@/components/common/ServerError';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/routes';
import { useCollectorAssignments } from '@/features/collector/hooks/use-collector-assignments';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { SubmissionTimeline } from '@/features/consumer/components/SubmissionTimeline';
import { formatDateTime, formatWeight } from '@/features/consumer/lib/submission-display';
import { AssignmentActionButton } from '@/features/collector/components/AssignmentActionButton';
import { AWAITING_RECYCLER_MESSAGE } from '@/features/collector/lib/assignment-display';

/** A labelled value row within the details card. */
function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-2 sm:flex-row sm:gap-4">
      <dt className="text-sm font-medium text-muted-foreground sm:w-40 sm:shrink-0">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

/**
 * Collector assignment detail view: full record, read-only pickup timeline, and
 * the single legal workflow action.
 *
 * The record is sourced from the collector's assignment queue cache rather than
 * GET /submissions/:id — that endpoint is owner/admin-only, so a collector may
 * only read submissions that appear in their own queue. A pickup that has left
 * the active queue (e.g. COLLECTED) or an unknown id therefore renders the
 * shared NotFound screen.
 */
export default function CollectorAssignmentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isPending, isError, refetch } = useCollectorAssignments();

  if (isPending) {
    return <PageLoader />;
  }

  if (isError) {
    return <ServerError onRetry={() => void refetch()} />;
  }

  const assignment = data.find((item) => item.id === id);
  if (!assignment) {
    return <NotFound />;
  }

  const readOnly = assignment.status === 'COLLECTED';

  return (
    <div className="flex flex-col gap-6">
      <DashboardHeader
        title={assignment.category}
        description="Assignment details and pickup lifecycle."
        actions={
          <Button variant="outline" onClick={() => navigate(ROUTES.collector)}>
            Back to dashboard
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <SubmissionStatusBadge status={assignment.status} />
        {readOnly ? (
          <p className="text-sm text-muted-foreground">{AWAITING_RECYCLER_MESSAGE}</p>
        ) : (
          <AssignmentActionButton
            submission={assignment}
            size="default"
            onDone={() => navigate(ROUTES.collector)}
          />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ContentCard title="Details">
            <dl className="divide-y">
              <DetailRow label="Category">{assignment.category}</DetailRow>
              <DetailRow label="Description">
                {assignment.description ?? <span className="text-muted-foreground">—</span>}
              </DetailRow>
              <DetailRow label="Estimated weight">
                {formatWeight(assignment.estimatedWeight)}
              </DetailRow>
              <DetailRow label="Address">{assignment.address}</DetailRow>
              <DetailRow label="Coordinates">
                {assignment.latitude}, {assignment.longitude}
              </DetailRow>
              <DetailRow label="Images">
                {assignment.imageUrls.length === 0 ? (
                  <span className="text-muted-foreground">No images</span>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {assignment.imageUrls.map((url) => (
                      <li key={url}>
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline underline-offset-4 break-all"
                        >
                          {url}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </DetailRow>
              <DetailRow label="Assigned collector">
                {assignment.assignedCollectorId ?? <span className="text-muted-foreground">—</span>}
              </DetailRow>
              <DetailRow label="Created">{formatDateTime(assignment.createdAt)}</DetailRow>
            </dl>
          </ContentCard>
        </div>

        <div>
          <Section title="Pickup lifecycle">
            <ContentCard>
              <SubmissionTimeline status={assignment.status} />
            </ContentCard>
          </Section>
        </div>
      </div>
    </div>
  );
}
