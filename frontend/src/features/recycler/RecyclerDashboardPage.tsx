import { useState } from 'react';
import { Link } from 'react-router-dom';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { SkeletonCards } from '@/components/dashboard/SkeletonCards';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { ServerError } from '@/components/common/ServerError';
import { icons } from '@/lib/icons';
import { ROUTES } from '@/lib/routes';
import { useAuth } from '@/hooks/use-auth';
import type { CompleteRecyclingResult } from '@/types';
import { useRecyclerAssignments } from '@/features/recycler/hooks/use-recycler-assignments';
import { RecyclerStatusSummary } from '@/features/recycler/components/RecyclerStatusSummary';
import { RecyclerAssignmentsTable } from '@/features/recycler/components/RecyclerAssignmentsTable';
import { RewardSuccessDialog } from '@/features/recycler/components/RewardSuccessDialog';
import { activeRecycling, computeRecyclerSummary } from '@/features/recycler/lib/recycler-display';

/** A quick-action tile linking to a common recycler task. */
function QuickAction({
  to,
  icon,
  title,
  description,
}: {
  to: string;
  icon: keyof typeof icons;
  title: string;
  description: string;
}) {
  const Icon = icons[icon];
  return (
    <Link
      to={to}
      className="flex items-start gap-3 rounded-lg border p-4 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <span className="rounded-md bg-muted p-2 text-muted-foreground" aria-hidden="true">
        <Icon className="size-5" />
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-muted-foreground">{description}</span>
      </span>
    </Link>
  );
}

/**
 * Recycler dashboard: welcome header, status summary, active recycling jobs,
 * today's recycling, and quick actions. All data comes from the real backend
 * via the assignment queue hook; loading, error, and empty states reuse the
 * shared framework components. The active queue drives every section and the
 * summary counts, so no extra API calls are made.
 *
 * Completing a job returns a backend-issued reward, which is surfaced in the
 * shared RewardSuccessDialog (values are displayed exactly as returned, never
 * recomputed).
 */
export default function RecyclerDashboardPage() {
  const { user } = useAuth();
  const { data, isPending, isError, refetch } = useRecyclerAssignments();
  const [reward, setReward] = useState<CompleteRecyclingResult | null>(null);
  const firstName = user?.fullName?.split(' ')[0] ?? 'there';

  const assignments = data ?? [];
  const summary = computeRecyclerSummary(assignments);
  const active = activeRecycling(assignments);

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title={`Welcome back, ${firstName}`}
        description="Process collected e-waste and record material recovery."
      />

      <Section title="Status summary" description="Your active recycling workload at a glance.">
        {isPending ? (
          <SkeletonCards count={4} className="lg:grid-cols-4" />
        ) : isError ? (
          <ServerError onRetry={() => void refetch()} />
        ) : (
          <RecyclerStatusSummary summary={summary} />
        )}
      </Section>

      <Section
        title="Active recycling"
        description="Every submission currently assigned to you for recycling."
      >
        {isPending ? (
          <SkeletonTable rows={5} columns={5} />
        ) : isError ? (
          <ServerError onRetry={() => void refetch()} />
        ) : assignments.length === 0 ? (
          <EmptyState
            icon="recycler"
            title="No recycling jobs"
            description="There are currently no submissions assigned for recycling."
          />
        ) : (
          <ContentCard>
            <RecyclerAssignmentsTable assignments={assignments} onCompleted={setReward} />
          </ContentCard>
        )}
      </Section>

      {!isPending && !isError && active.length > 0 && (
        <Section
          title="Today's recycling"
          description="Jobs you are currently processing and can complete."
        >
          <ContentCard>
            <RecyclerAssignmentsTable assignments={active} onCompleted={setReward} />
          </ContentCard>
        </Section>
      )}

      <Section title="Quick actions">
        <div className="grid gap-3 sm:grid-cols-2">
          <QuickAction
            to={ROUTES.recycler}
            icon="recycler"
            title="Active recycling"
            description="Review and process your assigned jobs"
          />
          <QuickAction
            to={ROUTES.settings}
            icon="settings"
            title="Settings"
            description="Manage your account preferences"
          />
        </div>
      </Section>

      <RewardSuccessDialog result={reward} onClose={() => setReward(null)} />
    </div>
  );
}
