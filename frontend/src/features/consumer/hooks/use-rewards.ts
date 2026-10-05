/**
 * Reward data hooks.
 *
 * TanStack Query wrappers around the reward API. Read-only for consumers:
 * balance and history are refreshed by submission mutations via the shared
 * `rewards.all` key (rewards are issued server-side, never from the client).
 */
import { useQuery } from '@tanstack/react-query';
import { rewardApi } from '@/api/reward.api';
import { queryKeys } from '@/lib/query-keys';
import type { PaginationParams } from '@/types';

/** The caller's GreenCoins balance and cumulative sustainability metrics. */
export function useRewardBalance() {
  return useQuery({
    queryKey: queryKeys.rewards.balance,
    queryFn: () => rewardApi.getBalance(),
  });
}

/** The caller's reward transaction history with submission context. */
export function useRewardHistory(params?: PaginationParams) {
  return useQuery({
    queryKey: queryKeys.rewards.history(params),
    queryFn: () => rewardApi.getHistory(params),
  });
}
