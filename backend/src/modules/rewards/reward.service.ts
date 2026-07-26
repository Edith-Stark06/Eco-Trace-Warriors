import { RewardReason } from '@prisma/client';
import { ConflictError, NotFoundError } from '@shared/errors';
import type { Logger } from '@shared/logging';
import type { Pagination } from '@shared/pagination';
import type { SubmissionRepository } from '../submission/submission.repository';
import type {
  RewardRepository,
  RewardTransactionResult,
  RewardTransactionWithSubmission,
  SustainabilityMetricsInput,
} from './reward.repository';

// ---------------------------------------------------------------------------
// Reward point mapping
// ---------------------------------------------------------------------------

/**
 * Base reward points per device category. Isolated to a single constant so the
 * entire mapping can be replaced (e.g. with a DB-backed config) without
 * touching the calculation logic.
 */
const REWARD_POINTS_MAP: Readonly<Record<string, number>> = {
  LAPTOP: 100,
  DESKTOP: 150,
  MOBILE: 50,
  TABLET: 60,
  MONITOR: 70,
  PRINTER: 80,
};

/** Points awarded when the submission category does not match any known device. */
const DEFAULT_REWARD_POINTS = 25;

/** GreenCoins earned per kilogram of estimated weight. */
const WEIGHT_BONUS_PER_KG = 5;

// ---------------------------------------------------------------------------
// Environmental-impact constants
// ---------------------------------------------------------------------------

interface ImpactConstants {
  readonly co2PerKg: number;
  readonly energyPerKg: number;
  readonly landfillPerKg: number;
}

/**
 * CO₂, energy, and landfill diversion factors per device category.
 * Like the reward mapping, this is isolated for easy replacement.
 */
const IMPACT_MAP: Readonly<Record<string, ImpactConstants>> = {
  LAPTOP: { co2PerKg: 25, energyPerKg: 15, landfillPerKg: 1 },
  MOBILE: { co2PerKg: 12, energyPerKg: 8, landfillPerKg: 1 },
  DESKTOP: { co2PerKg: 30, energyPerKg: 18, landfillPerKg: 1 },
};

/**
 * Conservative default impact factors used when the submission category does
 * not match any known device. Set lower than the lowest known device so
 * unclassified e-waste is not overestimated.
 */
const DEFAULT_IMPACT: ImpactConstants = {
  co2PerKg: 10,
  energyPerKg: 6,
  landfillPerKg: 1,
};

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** Sustainability metrics as computed by the service. */
export interface SustainabilityResult {
  readonly co2Saved: number;
  readonly energySaved: number;
  readonly landfillDiverted: number;
  readonly co2Unit: 'kg';
  readonly energyUnit: 'kWh';
  readonly landfillUnit: 'kg';
}

/** The reward summary returned to callers of {@link RewardService.issueReward}. */
export interface RewardSummary {
  readonly rewardTransaction: {
    readonly id: string;
    readonly submissionId: string;
    readonly points: number;
    readonly reason: string;
    readonly createdAt: string;
  };
  readonly greenCoinsAwarded: number;
  readonly updatedBalance: number;
  readonly sustainability: SustainabilityResult;
}

// ---------------------------------------------------------------------------
// Service interface & dependencies
// ---------------------------------------------------------------------------

/** Dependencies injected into the reward service. */
export interface RewardServiceDeps {
  readonly rewards: RewardRepository;
  readonly submissions: SubmissionRepository;
  readonly logger: Logger;
}

/** Balance snapshot returned by {@link RewardService.getBalance}. */
export interface RewardBalance {
  readonly greenCoins: number;
  readonly totalRewards: number;
  readonly totalCO2Saved: number;
  readonly totalEnergySaved: number;
  readonly totalLandfillDiverted: number;
}

export interface RewardService {
  /**
   * Issues a reward for a completed, recycled submission.
   *
   * Orchestrates the full workflow: load submission → validate →
   * calculate points → calculate impact → persist atomically → return summary.
   */
  issueReward(submissionId: string): Promise<RewardSummary>;

  /** Returns the reward transaction history for a given user. */
  getRewardHistory(
    userId: string,
    pagination?: Pagination,
  ): Promise<RewardTransactionWithSubmission[]>;

  /** Returns the current reward balance and cumulative sustainability metrics. */
  getBalance(userId: string): Promise<RewardBalance>;

  /** Calculates reward points for a given device category and weight. */
  calculateRewardPoints(category: string, estimatedWeight: number): number;

  /** Calculates environmental-impact metrics for a given device category and weight. */
  calculateEnvironmentalImpact(category: string, estimatedWeight: number): SustainabilityResult;
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

function normaliseCategory(category: string): string {
  return category.trim().toUpperCase();
}

function lookupBasePoints(category: string): number {
  return REWARD_POINTS_MAP[normaliseCategory(category)] ?? DEFAULT_REWARD_POINTS;
}

function lookupImpactConstants(category: string): ImpactConstants {
  return IMPACT_MAP[normaliseCategory(category)] ?? DEFAULT_IMPACT;
}

function toSustainabilityResult(impact: ImpactConstants, weight: number): SustainabilityResult {
  return {
    co2Saved: weight * impact.co2PerKg,
    energySaved: weight * impact.energyPerKg,
    landfillDiverted: weight * impact.landfillPerKg,
    co2Unit: 'kg',
    energyUnit: 'kWh',
    landfillUnit: 'kg',
  };
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/** Creates the reward service. Framework-agnostic and fully unit-testable. */
export function createRewardService(deps: RewardServiceDeps): RewardService {
  return {
    // -----------------------------------------------------------------------
    // Public API
    // -----------------------------------------------------------------------

    async issueReward(submissionId: string): Promise<RewardSummary> {
      // 1. Load submission
      const submission = await deps.submissions.findById(submissionId);
      if (!submission) {
        throw new NotFoundError('Submission not found.');
      }

      // 2. Validate submission status — only fully recycled submissions qualify
      if (submission.status !== 'RECYCLED') {
        throw new ConflictError(
          `Cannot issue reward for submission with status ${submission.status}. ` +
            'Submission must be RECYCLED.',
        );
      }

      // 3. Prevent duplicate reward — check whether a reward transaction already
      //    exists for this submission (idempotency guard).
      const existing = await deps.rewards.findRewardBySubmissionId(submissionId);
      if (existing) {
        throw new ConflictError('Reward has already been issued for this submission.');
      }

      // 4. Calculate reward points
      const points = this.calculateRewardPoints(submission.category, submission.estimatedWeight);

      // 5. Calculate sustainability metrics
      const sustainability = this.calculateEnvironmentalImpact(
        submission.category,
        submission.estimatedWeight,
      );

      const metrics: SustainabilityMetricsInput = {
        co2Saved: sustainability.co2Saved,
        energySaved: sustainability.energySaved,
        landfillDiverted: sustainability.landfillDiverted,
      };

      // 6. Execute repository transaction (atomic: reward + greenCoins + submission)
      let result: RewardTransactionResult;
      try {
        result = await deps.rewards.executeRewardTransaction(
          submission.userId,
          submissionId,
          points,
          RewardReason.RECYCLING,
          metrics,
        );
      } catch (err) {
        deps.logger.error({ submissionId, err }, 'Failed to issue reward');
        throw new ConflictError('Failed to issue reward. Please try again.');
      }

      deps.logger.info(
        { submissionId, userId: submission.userId, points, greenCoins: result.user.greenCoins },
        'Reward issued for recycled submission',
      );

      // 7. Return reward summary
      return {
        rewardTransaction: {
          id: result.reward.id,
          submissionId: result.reward.submissionId,
          points: result.reward.points,
          reason: result.reward.reason,
          createdAt: result.reward.createdAt.toISOString(),
        },
        greenCoinsAwarded: points,
        updatedBalance: result.user.greenCoins,
        sustainability,
      };
    },

    calculateRewardPoints(category: string, estimatedWeight: number): number {
      const basePoints = lookupBasePoints(category);
      const weightBonus = Math.round(estimatedWeight * WEIGHT_BONUS_PER_KG);
      return basePoints + weightBonus;
    },

    calculateEnvironmentalImpact(category: string, estimatedWeight: number): SustainabilityResult {
      const impact = lookupImpactConstants(category);
      return toSustainabilityResult(impact, estimatedWeight);
    },

    async getRewardHistory(
      userId: string,
      pagination?: Pagination,
    ): Promise<RewardTransactionWithSubmission[]> {
      const history = await deps.rewards.findRewardHistoryByUserId(userId, pagination);
      deps.logger.info({ userId, count: history.length }, 'Reward history requested');
      return history;
    },

    async getBalance(userId: string): Promise<RewardBalance> {
      const [userCoins, history] = await Promise.all([
        deps.rewards.getUserGreenCoins(userId),
        deps.rewards.findRewardHistoryByUserId(userId),
      ]);

      let totalRewards = 0;
      let totalCO2Saved = 0;
      let totalEnergySaved = 0;
      let totalLandfillDiverted = 0;

      for (const tx of history) {
        totalRewards += tx.points;
        const weight = tx.submission.estimatedWeight;
        const impact = lookupImpactConstants(tx.submission.category);
        totalCO2Saved += weight * impact.co2PerKg;
        totalEnergySaved += weight * impact.energyPerKg;
        totalLandfillDiverted += weight * impact.landfillPerKg;
      }

      deps.logger.info({ userId }, 'Reward balance requested');

      return {
        greenCoins: userCoins.greenCoins,
        totalRewards,
        totalCO2Saved,
        totalEnergySaved,
        totalLandfillDiverted,
      };
    },
  };
}
