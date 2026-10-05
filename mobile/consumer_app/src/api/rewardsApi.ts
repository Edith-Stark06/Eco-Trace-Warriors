import { apiClient } from './client';
import type { RewardBalance, RewardTransactionWithSubmission } from '../types/rewards';

/** Real backend routes — backend/src/modules/rewards/reward.routes.ts. Self-serve, no role guard. */
export const rewardsApi = {
  balance(): Promise<RewardBalance> {
    return apiClient<RewardBalance>('/rewards/balance');
  },
  history(): Promise<readonly RewardTransactionWithSubmission[]> {
    return apiClient<readonly RewardTransactionWithSubmission[]>('/rewards/history');
  },
};
