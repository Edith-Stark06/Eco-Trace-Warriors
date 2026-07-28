/**
 * Admin presentation helpers.
 *
 * Pure functions for the admin module. Kept free of React so they are
 * trivially unit-testable and reused across admin components.
 */

/** True when a submission is eligible for manual reward issuance.
 *  Backend requires status RECYCLED and no existing reward (idempotency guard). */
export function isRewardIssuable(status: string, rewardIssued?: boolean): boolean {
  return status === 'RECYCLED' && !rewardIssued;
}

/** True when a collector can be assigned — backend allows assign only while PENDING. */
export function isCollectorAssignable(status: string): boolean {
  return status === 'PENDING';
}

/** True when a recycler can be assigned — backend requires the item be COLLECTED. */
export function isRecyclerAssignable(status: string): boolean {
  return status === 'COLLECTED';
}

/** Short label for the reward issue button. */
export const ISSUE_REWARD_LABEL = 'Issue Reward';

/** Message shown when reward issuance is not available for a submission. */
export const REWARD_NOT_ISSUABLE_MESSAGE =
  'Rewards can only be issued for RECYCLED submissions that have not yet received one.';
