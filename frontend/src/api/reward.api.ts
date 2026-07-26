/**
 * Reward API module (placeholders).
 *
 * Typed wrappers around the rewards endpoints from
 * docs/engineering/05_API.md. Sprint 9.1 defines the surface only.
 */
import { notImplemented } from '@/api/not-implemented';
import type { PaginationParams } from '@/types';

export const rewardApi = {
  /** GET /rewards/balance */
  getBalance: (): Promise<unknown> => notImplemented('rewardApi.getBalance'),

  /** GET /rewards/transactions */
  getTransactions: (_params?: PaginationParams): Promise<unknown[]> =>
    notImplemented('rewardApi.getTransactions'),

  /** POST /rewards/redeem */
  redeem: (_payload: unknown): Promise<unknown> => notImplemented('rewardApi.redeem'),
};
