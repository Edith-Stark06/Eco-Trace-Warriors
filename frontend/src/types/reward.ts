/**
 * Reward domain types.
 *
 * Mirror the backend contract for the rewards module exactly
 * (backend/src/modules/rewards/*, docs/engineering/05_API.md). Keep in sync
 * when the backend contract changes.
 */

/** Reasons a reward transaction can be issued (Prisma `RewardReason`). */
export const REWARD_REASONS = [
  'RECYCLING',
  'BONUS',
  'CAMPAIGN',
  'ADJUSTMENT',
  'REDEMPTION',
] as const;

export type RewardReason = (typeof REWARD_REASONS)[number];

/**
 * Balance snapshot returned by GET /rewards/balance (`RewardBalance`).
 * `greenCoins` is the spendable balance; the totals are cumulative lifetime
 * metrics computed from the caller's reward history.
 */
export interface RewardBalance {
  greenCoins: number;
  totalRewards: number;
  totalCO2Saved: number;
  totalEnergySaved: number;
  totalLandfillDiverted: number;
}

/**
 * Sustainability metrics attached to a freshly issued reward, mirroring the
 * backend `SustainabilityResult`. Values are absolute quantities; the unit for
 * each is carried alongside it so the UI never hardcodes units.
 */
export interface RewardSustainability {
  co2Saved: number;
  energySaved: number;
  landfillDiverted: number;
  co2Unit: 'kg';
  energyUnit: 'kWh';
  landfillUnit: 'kg';
}

/**
 * The persisted reward transaction record returned inside a {@link RewardSummary}
 * (backend `RewardSummary.rewardTransaction`). `createdAt` is an ISO string.
 */
export interface RewardTransactionSummary {
  id: string;
  submissionId: string;
  points: number;
  reason: string;
  createdAt: string;
}

/**
 * The reward issued by the backend when a recycler completes a submission
 * (backend `RewardSummary`, returned by PATCH /submissions/:id/recycle/complete).
 * These are authoritative backend values — the frontend only displays them and
 * never recomputes any figure.
 */
export interface RewardSummary {
  rewardTransaction: RewardTransactionSummary;
  greenCoinsAwarded: number;
  updatedBalance: number;
  sustainability: RewardSustainability;
}

/**
 * A single reward transaction with its related submission context, as returned
 * by GET /rewards/history (`RewardTransactionWithSubmission`). `createdAt`
 * fields are ISO strings.
 */
export interface RewardHistoryItem {
  id: string;
  userId: string;
  submissionId: string;
  points: number;
  reason: RewardReason;
  createdAt: string;
  submission: {
    id: string;
    category: string;
    status: string;
    estimatedWeight: number;
    createdAt: string;
  };
}
