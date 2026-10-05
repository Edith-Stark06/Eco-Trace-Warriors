/** Mirrors backend/src/modules/rewards/reward.service.ts / reward.repository.ts. */
export interface RewardBalance {
  greenCoins: number;
  totalRewards: number;
  totalCO2Saved: number;
  totalEnergySaved: number;
  totalLandfillDiverted: number;
}

/** GET /rewards/history item — mirrors RewardTransactionWithSubmission. */
export interface RewardTransactionWithSubmission {
  id: string;
  userId: string;
  submissionId: string;
  points: number;
  reason: string;
  createdAt: string;
  submission: {
    id: string;
    category: string;
    status: string;
    estimatedWeight: number;
    createdAt: string;
  };
}
