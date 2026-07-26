import { Link } from 'react-router-dom';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { ServerError } from '@/components/common/ServerError';
import { Button } from '@/components/ui/button';
import { icons } from '@/lib/icons';
import { ROUTES } from '@/lib/routes';
import { useAuth } from '@/hooks/use-auth';
import { useSubmissions } from '@/features/consumer/hooks/use-submissions';
import { useRewardBalance } from '@/features/consumer/hooks/use-rewards';
import { RewardSummary } from '@/features/consumer/components/RewardSummary';
import { SubmissionsTable } from '@/features/consumer/components/SubmissionsTable';
import { CreateSubmissionDialog } from '@/features/consumer/components/CreateSubmissionDialog';
import { sortByNewest } from '@/features/consumer/lib/submission-display';

/** Number of most-recent submissions shown on the dashboard. */
const RECENT_LIMIT = 5;

/** A quick-action tile linking to a common consumer task. */
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
 * Consumer dashboard: welcome header, reward summary, recent submissions, and
 * quick actions. All data comes from the real backend via React Query hooks;
 * loading, error, and empty states reuse the shared framework components.
 */
export default function ConsumerDashboardPage() {
  const { user } = useAuth();
  const submissionsQuery = useSubmissions();
  const balanceQuery = useRewardBalance();

  const recent = submissionsQuery.data
    ? sortByNewest(submissionsQuery.data).slice(0, RECENT_LIMIT)
    : [];
  const firstName = user?.fullName?.split(' ')[0] ?? 'there';

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title={`Welcome back, ${firstName}`}
        description="Track your e-waste submissions, rewards, and environmental impact."
        actions={<CreateSubmissionDialog />}
      />

      <Section
        title="Rewards & impact"
        description="Your GreenCoins and lifetime sustainability contribution."
      >
        <RewardSummary
          balance={balanceQuery.data}
          isLoading={balanceQuery.isPending}
          isError={balanceQuery.isError}
          onRetry={() => void balanceQuery.refetch()}
        />
      </Section>

      <Section
        title="Recent submissions"
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to={ROUTES.consumerSubmissions}>View all</Link>
          </Button>
        }
      >
        {submissionsQuery.isPending ? (
          <SkeletonTable rows={5} columns={6} />
        ) : submissionsQuery.isError ? (
          <ServerError onRetry={() => void submissionsQuery.refetch()} />
        ) : recent.length === 0 ? (
          <EmptyState
            icon="package"
            title="No submissions yet"
            description="Create your first e-waste submission to get started."
            action={<CreateSubmissionDialog />}
          />
        ) : (
          <ContentCard>
            <SubmissionsTable submissions={recent} />
          </ContentCard>
        )}
      </Section>

      <Section title="Quick actions">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <QuickAction
            to={ROUTES.consumerSubmissions}
            icon="package"
            title="Submissions"
            description="View and manage your submissions"
          />
          <QuickAction
            to={ROUTES.consumerRewards}
            icon="coins"
            title="Rewards"
            description="See your GreenCoins and history"
          />
          <QuickAction
            to={ROUTES.consumerSubmissions}
            icon="search"
            title="Submission history"
            description="Browse every submission you've made"
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
