import type { PrismaClient, RewardReason } from '@prisma/client';

/**
 * Repositories are the only place Prisma is used for the rewards module.
 * Services depend on these interfaces, never on Prisma directly —
 * see docs/engineering/06_BACKEND.md (Layering).
 */

// ---------------------------------------------------------------------------
// Input types
// ---------------------------------------------------------------------------

/** Input for creating a reward transaction row. */
export interface CreateRewardInput {
  readonly userId: string;
  readonly submissionId: string;
  readonly points: number;
  readonly reason: RewardReason;
}

/** Sustainability metrics stored on a submission when a reward is issued. */
export interface SustainabilityMetricsInput {
  readonly co2Saved?: number | undefined;
  readonly energySaved?: number | undefined;
  readonly landfillDiverted?: number | undefined;
}

// ---------------------------------------------------------------------------
// Record types
// ---------------------------------------------------------------------------

/** RewardTransaction row as read by the rewards module. */
export interface RewardTransactionRecord {
  readonly id: string;
  readonly userId: string;
  readonly submissionId: string;
  readonly points: number;
  readonly reason: RewardReason;
  readonly createdAt: Date;
}

/**
 * RewardTransaction with the related submission joined in.
 * Returned by methods that include submission context (history queries).
 */
export interface RewardTransactionWithSubmission extends RewardTransactionRecord {
  readonly submission: {
    readonly id: string;
    readonly category: string;
    readonly status: string;
    readonly estimatedWeight: number;
    readonly createdAt: Date;
  };
}

/** Projection of a user row returned after incrementing greenCoins. */
export interface GreenCoinsRecord {
  readonly id: string;
  readonly greenCoins: number;
}

/** Projection of a submission row returned after marking reward as issued. */
export interface RewardIssuedRecord {
  readonly id: string;
  readonly rewardIssued: boolean;
  readonly co2Saved: number | null;
  readonly energySaved: number | null;
  readonly landfillDiverted: number | null;
}

/**
 * Composite result returned by {@link RewardRepository.executeRewardTransaction}.
 * Contains every record affected by the atomic transaction.
 */
export interface RewardTransactionResult {
  readonly reward: RewardTransactionRecord;
  readonly user: GreenCoinsRecord;
  readonly submission: RewardIssuedRecord;
}

// ---------------------------------------------------------------------------
// Repository interface
// ---------------------------------------------------------------------------

export interface RewardRepository {
  createRewardTransaction(input: CreateRewardInput): Promise<RewardTransactionRecord>;
  findRewardBySubmissionId(submissionId: string): Promise<RewardTransactionRecord | null>;
  findRewardHistoryByUserId(userId: string): Promise<RewardTransactionWithSubmission[]>;
  incrementUserGreenCoins(userId: string, points: number): Promise<GreenCoinsRecord>;
  markSubmissionRewardIssued(
    submissionId: string,
    metrics: SustainabilityMetricsInput,
  ): Promise<RewardIssuedRecord>;
  executeRewardTransaction(
    userId: string,
    submissionId: string,
    points: number,
    reason: RewardReason,
    metrics: SustainabilityMetricsInput,
  ): Promise<RewardTransactionResult>;
}

// ---------------------------------------------------------------------------
// Select projections
// ---------------------------------------------------------------------------

const rewardTransactionSelect = {
  id: true,
  userId: true,
  submissionId: true,
  points: true,
  reason: true,
  createdAt: true,
} as const;

const rewardTransactionWithSubmissionSelect = {
  id: true,
  userId: true,
  submissionId: true,
  points: true,
  reason: true,
  createdAt: true,
  submission: {
    select: {
      id: true,
      category: true,
      status: true,
      estimatedWeight: true,
      createdAt: true,
    },
  },
} as const;

const greenCoinsSelect = {
  id: true,
  greenCoins: true,
} as const;

const rewardIssuedSelect = {
  id: true,
  rewardIssued: true,
  co2Saved: true,
  energySaved: true,
  landfillDiverted: true,
} as const;

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/** Creates the reward repository backed by Prisma. */
export function createRewardRepository(deps: { readonly prisma: PrismaClient }): RewardRepository {
  const { prisma } = deps;

  return {
    // -----------------------------------------------------------------------
    // Single-record operations
    // -----------------------------------------------------------------------

    async createRewardTransaction(input: CreateRewardInput): Promise<RewardTransactionRecord> {
      return prisma.rewardTransaction.create({
        data: {
          userId: input.userId,
          submissionId: input.submissionId,
          points: input.points,
          reason: input.reason,
        },
        select: rewardTransactionSelect,
      });
    },

    async findRewardBySubmissionId(submissionId: string): Promise<RewardTransactionRecord | null> {
      return prisma.rewardTransaction.findUnique({
        where: { submissionId },
        select: rewardTransactionSelect,
      });
    },

    async findRewardHistoryByUserId(userId: string): Promise<RewardTransactionWithSubmission[]> {
      return prisma.rewardTransaction.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        select: rewardTransactionWithSubmissionSelect,
      });
    },

    async incrementUserGreenCoins(userId: string, points: number): Promise<GreenCoinsRecord> {
      return prisma.user.update({
        where: { id: userId },
        data: { greenCoins: { increment: points } },
        select: greenCoinsSelect,
      });
    },

    async markSubmissionRewardIssued(
      submissionId: string,
      metrics: SustainabilityMetricsInput,
    ): Promise<RewardIssuedRecord> {
      return prisma.submission.update({
        where: { id: submissionId },
        data: {
          rewardIssued: true,
          co2Saved: metrics.co2Saved ?? null,
          energySaved: metrics.energySaved ?? null,
          landfillDiverted: metrics.landfillDiverted ?? null,
        },
        select: rewardIssuedSelect,
      });
    },

    // -----------------------------------------------------------------------
    // Composite transaction (all-or-nothing)
    // -----------------------------------------------------------------------

    async executeRewardTransaction(
      userId: string,
      submissionId: string,
      points: number,
      reason: RewardReason,
      metrics: SustainabilityMetricsInput,
    ): Promise<RewardTransactionResult> {
      return prisma.$transaction(async (tx) => {
        const reward = await tx.rewardTransaction.create({
          data: { userId, submissionId, points, reason },
          select: rewardTransactionSelect,
        });

        const user = await tx.user.update({
          where: { id: userId },
          data: { greenCoins: { increment: points } },
          select: greenCoinsSelect,
        });

        const submission = await tx.submission.update({
          where: { id: submissionId },
          data: {
            rewardIssued: true,
            co2Saved: metrics.co2Saved ?? null,
            energySaved: metrics.energySaved ?? null,
            landfillDiverted: metrics.landfillDiverted ?? null,
          },
          select: rewardIssuedSelect,
        });

        return { reward, user, submission };
      });
    },
  };
}
