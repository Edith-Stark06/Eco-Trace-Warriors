import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { PageLoader } from '@/components/dashboard/PageLoader';
import { NotFound } from '@/components/common/NotFound';
import { ServerError } from '@/components/common/ServerError';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/routes';
import type { CompleteRecyclingResult } from '@/types';
import { useRecyclerAssignments } from '@/features/recycler/hooks/use-recycler-assignments';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { SubmissionTimeline } from '@/features/consumer/components/SubmissionTimeline';
import { formatDateTime, formatWeight } from '@/features/consumer/lib/submission-display';
import { RecyclerActionButton } from '@/features/recycler/components/RecyclerActionButton';
import { RewardSuccessDialog } from '@/features/recycler/components/RewardSuccessDialog';
import {
  isReadOnlyForRecycler,
  materialRecoveryEntries,
  RECYCLED_LABEL,
} from '@/features/recycler/lib/recycler-display';

/** A labelled value row within the details card. */
function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-2 sm:flex-row sm:gap-4">
      <dt className="text-sm font-medium text-muted-foreground sm:w-40 sm:shrink-0">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

const EMPTY = <span className="text-muted-foreground">—</span>;

/**
 * Recycler assignment detail view: full record, read-only recycling timeline,
 * and the single legal workflow action.
 *
 * The record is sourced from the recycler's assignment-queue cache rather than
 * GET /submissions/:id — that endpoint is owner/admin-only, so a recycler may
 * only read submissions that appear in their own queue. A job that has left the
 * active queue (e.g. RECYCLED) or an unknown id therefore renders the shared
 * NotFound screen. Completing a job surfaces the backend reward in the shared
 * success dialog.
 */
export default function RecyclerAssignmentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isPending, isError, refetch } = useRecyclerAssignments();
  const [reward, setReward] = useState<CompleteRecyclingResult | null>(null);

  if (isPending) {
    return <PageLoader />;
  }

  if (isError) {
    return <ServerError onRetry={() => void refetch()} />;
  }

  const assignment = data.find((item) => item.id === id);
  if (!assignment) {
    // A just-completed job leaves the active queue on refetch. If we captured its
    // reward, keep showing that result instead of flashing NotFound; otherwise
    // the id is unknown or the job is no longer the recycler's to view.
    if (reward) {
      return (
        <div className="flex flex-col gap-6">
          <DashboardHeader
            title="Recycling completed"
            description="This job has been recycled and is no longer in your active queue."
            actions={
              <Button variant="outline" onClick={() => navigate(ROUTES.recycler)}>
                Back to dashboard
              </Button>
            }
          />
          <RewardSuccessDialog result={reward} onClose={() => navigate(ROUTES.recycler)} />
        </div>
      );
    }
    return <NotFound />;
  }

  const readOnly = isReadOnlyForRecycler(assignment.status);
  const materials = materialRecoveryEntries(assignment.materialRecovery);

  return (
    <div className="flex flex-col gap-6">
      <DashboardHeader
        title={assignment.category}
        description="Assignment details and recycling lifecycle."
        actions={
          <Button variant="outline" onClick={() => navigate(ROUTES.recycler)}>
            Back to dashboard
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <SubmissionStatusBadge status={assignment.status} />
        {readOnly ? (
          <p className="text-sm text-muted-foreground">{RECYCLED_LABEL}</p>
        ) : (
          <RecyclerActionButton
            submission={assignment}
            size="default"
            onStarted={() => navigate(ROUTES.recycler)}
            onCompleted={setReward}
          />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ContentCard title="Details">
            <dl className="divide-y">
              <DetailRow label="Category">{assignment.category}</DetailRow>
              <DetailRow label="Description">{assignment.description ?? EMPTY}</DetailRow>
              <DetailRow label="Estimated weight">
                {formatWeight(assignment.estimatedWeight)}
              </DetailRow>
              <DetailRow label="Recovered weight">
                {assignment.recoveredWeight != null
                  ? formatWeight(assignment.recoveredWeight)
                  : EMPTY}
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
              <DetailRow label="Recycler notes">{assignment.recyclerNotes ?? EMPTY}</DetailRow>
              <DetailRow label="Material recovery">
                {materials.length === 0 ? (
                  EMPTY
                ) : (
                  <ul className="flex flex-col gap-1">
                    {materials.map((material) => (
                      <li key={material.name} className="flex justify-between gap-4">
                        <span>{material.name}</span>
                        <span className="text-muted-foreground">
                          {formatWeight(material.weight)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </DetailRow>
              <DetailRow label="Collected">
                {assignment.completedAt ? formatDateTime(assignment.completedAt) : EMPTY}
              </DetailRow>
            </dl>
          </ContentCard>
        </div>

        <div>
          <Section title="Recycling lifecycle">
            <ContentCard>
              <SubmissionTimeline status={assignment.status} />
            </ContentCard>
          </Section>
        </div>
      </div>

      <RewardSuccessDialog result={reward} onClose={() => setReward(null)} />
    </div>
  );
}
