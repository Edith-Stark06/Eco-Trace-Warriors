import { Link } from 'react-router-dom';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { Section } from '@/components/dashboard/Section';
import { ContentCard } from '@/components/dashboard/ContentCard';
import { SkeletonTable } from '@/components/dashboard/SkeletonTable';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { ServerError } from '@/components/common/ServerError';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { consumerSubmissionPath } from '@/lib/routes';
import { useRewardBalance, useRewardHistory } from '@/features/consumer/hooks/use-rewards';
import { RewardSummary } from '@/features/consumer/components/RewardSummary';
import { SubmissionStatusBadge } from '@/features/consumer/components/SubmissionStatusBadge';
import { formatPoints, rewardReasonLabel } from '@/features/consumer/lib/reward-display';
import { formatDate } from '@/features/consumer/lib/submission-display';

/**
 * Consumer rewards page: a summary of GreenCoins and cumulative impact above a
 * table of individual reward transactions. Both come from the real backend via
 * React Query; loading, error, and empty states reuse the shared framework.
 */
export default function ConsumerRewardsPage() {
  const balanceQuery = useRewardBalance();
  const historyQuery = useRewardHistory();

  const history = historyQuery.data ?? [];

  return (
    <div className="flex flex-col gap-8">
      <DashboardHeader
        title="Rewards"
        description="Your GreenCoins, environmental impact, and reward history."
      />

      <Section title="Summary">
        <RewardSummary
          balance={balanceQuery.data}
          isLoading={balanceQuery.isPending}
          isError={balanceQuery.isError}
          onRetry={() => void balanceQuery.refetch()}
        />
      </Section>

      <Section title="Reward history">
        {historyQuery.isPending ? (
          <SkeletonTable rows={6} columns={5} />
        ) : historyQuery.isError ? (
          <ServerError onRetry={() => void historyQuery.refetch()} />
        ) : history.length === 0 ? (
          <EmptyState
            icon="coins"
            title="No rewards yet"
            description="You'll earn GreenCoins once your submissions are recycled."
          />
        ) : (
          <ContentCard>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Points</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Submission category</TableHead>
                  <TableHead>Submission status</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">+{formatPoints(item.points)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{rewardReasonLabel(item.reason)}</Badge>
                    </TableCell>
                    <TableCell>
                      <Link
                        to={consumerSubmissionPath(item.submissionId)}
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        {item.submission.category}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <SubmissionStatusBadge status={item.submission.status} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {formatDate(item.createdAt)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ContentCard>
        )}
      </Section>
    </div>
  );
}
