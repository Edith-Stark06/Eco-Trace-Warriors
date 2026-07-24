import { randomUUID } from 'node:crypto';
import type { RewardReason } from '@prisma/client';
import type {
  GreenCoinsRecord,
  RewardIssuedRecord,
  RewardRepository,
  RewardTransactionRecord,
  RewardTransactionResult,
  RewardTransactionWithSubmission,
  SustainabilityMetricsInput,
} from '@modules/rewards';

export function createInMemoryRewardRepository(): RewardRepository {
  const rewards = new Map<string, RewardTransactionRecord>();
  const rewardsBySubmission = new Map<string, RewardTransactionRecord>();
  const userCoins = new Map<string, number>();

  return {
    createRewardTransaction(input: {
      readonly userId: string;
      readonly submissionId: string;
      readonly points: number;
      readonly reason: RewardReason;
    }): Promise<RewardTransactionRecord> {
      const record: RewardTransactionRecord = {
        id: randomUUID(),
        userId: input.userId,
        submissionId: input.submissionId,
        points: input.points,
        reason: input.reason,
        createdAt: new Date(),
      };
      rewards.set(record.id, record);
      rewardsBySubmission.set(input.submissionId, record);
      return Promise.resolve(record);
    },

    findRewardBySubmissionId(submissionId: string): Promise<RewardTransactionRecord | null> {
      return Promise.resolve(rewardsBySubmission.get(submissionId) ?? null);
    },

    findRewardHistoryByUserId(_userId: string): Promise<RewardTransactionWithSubmission[]> {
      return Promise.resolve([]);
    },

    getUserGreenCoins(userId: string): Promise<GreenCoinsRecord> {
      return Promise.resolve({ id: userId, greenCoins: userCoins.get(userId) ?? 0 });
    },

    incrementUserGreenCoins(userId: string, points: number): Promise<GreenCoinsRecord> {
      const current = userCoins.get(userId) ?? 0;
      const updated = current + points;
      userCoins.set(userId, updated);
      return Promise.resolve({ id: userId, greenCoins: updated });
    },

    markSubmissionRewardIssued(
      submissionId: string,
      metrics: SustainabilityMetricsInput,
    ): Promise<RewardIssuedRecord> {
      return Promise.resolve({
        id: submissionId,
        rewardIssued: true,
        co2Saved: metrics.co2Saved ?? null,
        energySaved: metrics.energySaved ?? null,
        landfillDiverted: metrics.landfillDiverted ?? null,
      });
    },

    async executeRewardTransaction(
      userId: string,
      submissionId: string,
      points: number,
      reason: RewardReason,
      metrics: SustainabilityMetricsInput,
    ): Promise<RewardTransactionResult> {
      const reward = await this.createRewardTransaction({ userId, submissionId, points, reason });
      const user = await this.incrementUserGreenCoins(userId, points);
      const submission = await this.markSubmissionRewardIssued(submissionId, metrics);
      return { reward, user, submission };
    },
  };
}
