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
import { useCollectorAssignments } from '@/features/collector/hooks/use-collector-assignments';
import { StatusSummary } from '@/features/collector/components/StatusSummary';
import { AssignmentsTable } from '@/features/collector/components/AssignmentsTable';
import { computeStatusSummary, todaysWork } from '@/features/collector/lib/assignment-display';

/** A quick-action tile linking to a common collector task. */
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
 * Collector dashboard: welcome header, status summary, active assignments,
 * today's work, and quick actions. All data comes from the real backend via
 * the assignment queue hook; loading, error, and empty states reuse the shared
 * framework components. The active queue drives every section and the summary
 * counts, so no extra API calls are made.
 */
export default function CollectorDashboardPage() {
  const { user } = useAuth();
  const { data, isPending, isError, refetch } = useCollectorAssignments();
  const firstName = user?.fullName?.split(' ')[0] ?? 'there';

  const assignments = data ?? [];
  const summary = computeStatusSummary(assignments);
  const active = todaysWork(assignments);

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title={`Welcome back, ${firstName}`}
        description="Manage your assigned pickups and keep the e-waste lifecycle moving."
      />

      <Section title="Status summary" description="Your active pickup workload at a glance.">
        {isPending ? (
          <SkeletonCards count={4} className="lg:grid-cols-4" />
        ) : isError ? (
          <ServerError onRetry={() => void refetch()} />
        ) : (
          <StatusSummary summary={summary} />
        )}
      </Section>

      <Section title="Active assignments" description="Every pickup currently assigned to you.">
        {isPending ? (
          <SkeletonTable rows={5} columns={6} />
        ) : isError ? (
          <ServerError onRetry={() => void refetch()} />
        ) : assignments.length === 0 ? (
          <EmptyState
            icon="collector"
            title="No active pickups"
            description="You currently have no assigned pickup requests."
          />
        ) : (
          <ContentCard>
            <AssignmentsTable assignments={assignments} />
          </ContentCard>
        )}
      </Section>

      {!isPending && !isError && active.length > 0 && (
        <Section
          title="Today's work"
          description="Pickups you have accepted or are currently collecting."
        >
          <ContentCard>
            <AssignmentsTable assignments={active} />
          </ContentCard>
        </Section>
      )}

      <Section title="Quick actions">
        <div className="grid gap-3 sm:grid-cols-2">
          <QuickAction
            to={ROUTES.collector}
            icon="collector"
            title="Active pickups"
            description="Review and act on your assigned pickups"
          />
          <QuickAction
            to={ROUTES.settings}
            icon="settings"
            title="Settings"
            description="Manage your account preferences"
          />
        </div>
      </Section>
    </div>
  );
}
