import { StatCard } from '@/components/dashboard/StatCard';
import { SkeletonCards } from '@/components/dashboard/SkeletonCards';
import { ServerError } from '@/components/common/ServerError';
import { EmptyState } from '@/components/dashboard/EmptyState';
import type { RewardBalance } from '@/types';
import { formatMetric, formatPoints } from '@/features/consumer/lib/reward-display';

interface RewardSummaryProps {
  balance: RewardBalance | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry?: () => void;
}

/**
 * Reward summary grid: GreenCoins, total rewards, and cumulative sustainability
 * metrics (CO₂ saved, energy saved, landfill diverted). Handles its own
 * loading, error, and empty presentation using the shared framework components
 * so pages just pass the query result through.
 */
export function RewardSummary({ balance, isLoading, isError, onRetry }: RewardSummaryProps) {
  if (isLoading) {
    return <SkeletonCards count={5} />;
  }

  if (isError || !balance) {
    return <ServerError onRetry={onRetry} />;
  }

  const hasActivity = balance.totalRewards > 0 || balance.greenCoins > 0;
  if (!hasActivity) {
    return (
      <EmptyState
        icon="coins"
        title="No rewards yet"
        description="Once your submissions are recycled, you'll earn GreenCoins and see your environmental impact here."
      />
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      <StatCard label="Green Coins" value={formatPoints(balance.greenCoins)} icon="coins" />
      <StatCard label="Total Rewards" value={formatPoints(balance.totalRewards)} icon="check" />
      <StatCard
        label="CO₂ Saved"
        value={formatMetric(balance.totalCO2Saved, 'kg')}
        icon="recycler"
      />
      <StatCard
        label="Energy Saved"
        value={formatMetric(balance.totalEnergySaved, 'kWh')}
        icon="dashboard"
      />
      <StatCard
        label="Landfill Diverted"
        value={formatMetric(balance.totalLandfillDiverted, 'kg')}
        icon="package"
      />
    </div>
  );
}
