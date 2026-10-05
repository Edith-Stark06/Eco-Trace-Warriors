import { useNavigate, useParams } from 'react-router-dom';
import { isAxiosError } from 'axios';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { PageLoader } from '@/components/dashboard/PageLoader';
import { NotFound } from '@/components/common/NotFound';
import { ServerError } from '@/components/common/ServerError';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/routes';
import { useSubmission } from '@/features/consumer/hooks/use-submissions';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { SubmissionTimeline } from '@/features/consumer/components/SubmissionTimeline';
import { EditSubmissionDialog } from '@/features/consumer/components/EditSubmissionDialog';
import { DeleteSubmissionDialog } from '@/features/consumer/components/DeleteSubmissionDialog';
import {
  IMMUTABLE_SUBMISSION_MESSAGE,
  formatDateTime,
  formatWeight,
  isSubmissionMutable,
} from '@/features/consumer/lib/submission-display';

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
 * Submission detail view: full record, read-only lifecycle timeline, and
 * owner actions. Edit and Delete are offered only while the submission is
 * PENDING (mirroring the backend rule); otherwise an explanatory message is
 * shown. A 404 from the backend renders the shared NotFound screen.
 */
export default function ConsumerSubmissionDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: submission, isPending, isError, error, refetch } = useSubmission(id);

  if (isPending) {
    return <PageLoader />;
  }

  if (isError) {
    if (isAxiosError(error) && error.response?.status === 404) {
      return <NotFound />;
    }
    return <ServerError onRetry={() => void refetch()} />;
  }

  const mutable = isSubmissionMutable(submission.status);

  return (
    <div className="flex flex-col gap-6">
      <DashboardHeader
        title={submission.category}
        description="Submission details and recycling lifecycle."
        actions={
          <Button variant="outline" onClick={() => navigate(ROUTES.consumerSubmissions)}>
            Back to submissions
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <SubmissionStatusBadge status={submission.status} />
        {mutable ? (
          <div className="flex items-center gap-2">
            <EditSubmissionDialog submission={submission} />
            <DeleteSubmissionDialog
              submission={submission}
              onDeleted={() => navigate(ROUTES.consumerSubmissions)}
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{IMMUTABLE_SUBMISSION_MESSAGE}</p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ContentCard title="Details">
            <dl className="divide-y">
              <DetailRow label="Category">{submission.category}</DetailRow>
              <DetailRow label="Description">
                {submission.description ?? <span className="text-muted-foreground">—</span>}
              </DetailRow>
              <DetailRow label="Estimated weight">
                {formatWeight(submission.estimatedWeight)}
              </DetailRow>
              <DetailRow label="Address">{submission.address}</DetailRow>
              <DetailRow label="Latitude">{submission.latitude}</DetailRow>
              <DetailRow label="Longitude">{submission.longitude}</DetailRow>
              <DetailRow label="Image URLs">
                {submission.imageUrls.length === 0 ? (
                  <span className="text-muted-foreground">No images</span>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {submission.imageUrls.map((url) => (
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
              <DetailRow label="Created">{formatDateTime(submission.createdAt)}</DetailRow>
              <DetailRow label="Last updated">{formatDateTime(submission.updatedAt)}</DetailRow>
            </dl>
          </ContentCard>
        </div>

        <div>
          <Section title="Lifecycle">
            <ContentCard>
              <SubmissionTimeline status={submission.status} />
            </ContentCard>
          </Section>
        </div>
      </div>
    </div>
  );
}
