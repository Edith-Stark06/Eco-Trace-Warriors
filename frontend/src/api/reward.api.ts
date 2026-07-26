/**
 * Reward API module.
 *
 * Typed wrappers around the rewards endpoints from docs/engineering/05_API.md
 * (backend/src/modules/rewards), built on the single shared Axios instance.
 * Each method unwraps the success envelope (`response.data.data`) and returns
 * the resource directly. Consumers read their own balance and history; reward
 * issuance is an admin-only backend concern and is not exposed here.
 */
import { apiClient } from '@/api/axios';
import { unwrap } from '@/api/client';
import type { ApiSuccess, PaginationParams, RewardBalance, RewardHistoryItem } from '@/types';

export const rewardApi = {
  /** GET /rewards/balance — the caller's GreenCoins balance and lifetime impact. */
  getBalance: (): Promise<RewardBalance> =>
    unwrap<RewardBalance>(apiClient.get<ApiSuccess<RewardBalance>>('/rewards/balance')),

  /** GET /rewards/history — the caller's reward transactions with submission context. */
  getHistory: (params?: PaginationParams): Promise<RewardHistoryItem[]> =>
    unwrap<RewardHistoryItem[]>(
      apiClient.get<ApiSuccess<RewardHistoryItem[]>>('/rewards/history', { params }),
    ),
};
