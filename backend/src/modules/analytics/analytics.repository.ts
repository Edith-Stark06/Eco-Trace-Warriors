import type { PrismaClient, SubmissionStatus } from '@prisma/client';

/**
 * Repositories are the only place Prisma is used for the analytics module.
 * Services depend on this interface, never on Prisma directly —
 * see docs/engineering/06_BACKEND.md (Layering).
 *
 * Analytics is a read-only reporting layer over the existing Submission,
 * User, and RewardTransaction tables owned by the submission/auth/rewards
 * modules — it introduces no new domain tables of its own.
 */

/** Aggregated submission counts by lifecycle bucket. */
export interface SubmissionStatusCounts {
  readonly total: number;
  readonly pending: number;
  readonly inProgress: number;
  readonly collected: number;
  readonly recycled: number;
}

/** Aggregated weight totals across all submissions. */
export interface WeightTotals {
  readonly estimatedWeight: number;
  readonly recoveredWeight: number;
}

/** Aggregated user counts by role. */
export interface UserCounts {
  readonly total: number;
  readonly collectors: number;
  readonly recyclers: number;
}

/** Aggregated environmental-impact totals, persisted per-submission at reward time. */
export interface EnvironmentalImpactTotals {
  readonly co2Saved: number;
  readonly energySaved: number;
  readonly landfillDiverted: number;
}

/** One region's aggregated statistics. */
export interface RegionalAggregateRow {
  readonly region: string;
  readonly totalSubmissions: number;
  readonly totalWeight: number;
  readonly recycledWeight: number;
  readonly activeCollectors: number;
  readonly activeRecyclers: number;
}

/** One real daily observation for e-waste forecasting: the weight actually
 *  recycled on that calendar date (see `getDailyRecycledWeightSeries`). */
export interface DailyWeightObservation {
  readonly date: string;
  readonly weightKg: number;
}

export interface AnalyticsRepository {
  getSubmissionStatusCounts(): Promise<SubmissionStatusCounts>;
  getWeightTotals(): Promise<WeightTotals>;
  getUserCounts(): Promise<UserCounts>;
  getTotalRewardPoints(): Promise<number>;
  getEnvironmentalImpactTotals(): Promise<EnvironmentalImpactTotals>;
  getRegionalBreakdown(): Promise<RegionalAggregateRow[]>;
  /** Real daily recycled-weight history, for forecasting (see docstring on
   *  the implementation for the exact aggregation definition). */
  getDailyRecycledWeightSeries(): Promise<DailyWeightObservation[]>;
}

/** Statuses actively in flight between assignment and collection. */
const IN_PROGRESS_STATUSES: readonly SubmissionStatus[] = [
  'ASSIGNED',
  'ACCEPTED',
  'IN_PROGRESS',
  'RECYCLING',
];

/** Terminal, successfully-recycled statuses. */
const RECYCLED_STATUSES: readonly SubmissionStatus[] = ['RECYCLED', 'COMPLETED'];

/** Label used for submissions whose owner has not set a region. */
const UNSPECIFIED_REGION = 'Unspecified';

/** Raw row shape read for daily-weight aggregation (one per submission). */
export interface RecycledWeightRow {
  readonly recycledAt: Date;
  readonly recoveredWeight: number;
}

/**
 * Aggregates raw per-submission recycling rows into one real observation per
 * calendar date (UTC), summing same-day submissions rather than counting
 * them separately — this is the "duplicate submission" handling: two
 * submissions recycled on 2026-08-01 contribute one 2026-08-01 entry whose
 * weight is their sum, never two entries or a doubled/lost total.
 *
 * A pure function (no Prisma) so the aggregation logic is unit-testable
 * without a database — see `analytics.repository.test.ts`.
 */
export function aggregateDailyRecycledWeight(
  rows: readonly RecycledWeightRow[],
): DailyWeightObservation[] {
  const byDate = new Map<string, number>();
  for (const row of rows) {
    const dateKey = row.recycledAt.toISOString().slice(0, 10); // YYYY-MM-DD, UTC
    byDate.set(dateKey, (byDate.get(dateKey) ?? 0) + row.recoveredWeight);
  }
  return Array.from(byDate.entries())
    .map(([date, weightKg]) => ({ date, weightKg }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** Creates the analytics repository backed by Prisma. */
export function createAnalyticsRepository(deps: {
  readonly prisma: PrismaClient;
}): AnalyticsRepository {
  const { prisma } = deps;

  return {
    async getSubmissionStatusCounts(): Promise<SubmissionStatusCounts> {
      const grouped = await prisma.submission.groupBy({
        by: ['status'],
        _count: { _all: true },
      });

      let total = 0;
      let pending = 0;
      let inProgress = 0;
      let collected = 0;
      let recycled = 0;

      for (const row of grouped) {
        const count = row._count._all;
        total += count;
        if (row.status === 'PENDING') pending += count;
        else if (row.status === 'COLLECTED') collected += count;
        else if (IN_PROGRESS_STATUSES.includes(row.status)) inProgress += count;
        else if (RECYCLED_STATUSES.includes(row.status)) recycled += count;
      }

      return { total, pending, inProgress, collected, recycled };
    },

    async getWeightTotals(): Promise<WeightTotals> {
      const result = await prisma.submission.aggregate({
        _sum: { estimatedWeight: true, recoveredWeight: true },
      });
      return {
        estimatedWeight: result._sum.estimatedWeight ?? 0,
        recoveredWeight: result._sum.recoveredWeight ?? 0,
      };
    },

    async getUserCounts(): Promise<UserCounts> {
      const [total, collectors, recyclers] = await Promise.all([
        prisma.user.count(),
        prisma.user.count({ where: { role: { name: 'COLLECTOR' } } }),
        prisma.user.count({ where: { role: { name: 'RECYCLER' } } }),
      ]);
      return { total, collectors, recyclers };
    },

    async getTotalRewardPoints(): Promise<number> {
      const result = await prisma.rewardTransaction.aggregate({
        _sum: { points: true },
      });
      return result._sum.points ?? 0;
    },

    async getEnvironmentalImpactTotals(): Promise<EnvironmentalImpactTotals> {
      const result = await prisma.submission.aggregate({
        _sum: { co2Saved: true, energySaved: true, landfillDiverted: true },
      });
      return {
        co2Saved: result._sum.co2Saved ?? 0,
        energySaved: result._sum.energySaved ?? 0,
        landfillDiverted: result._sum.landfillDiverted ?? 0,
      };
    },

    async getRegionalBreakdown(): Promise<RegionalAggregateRow[]> {
      // Region lives on the submission owner (User.region), not on Submission
      // itself, and Prisma's groupBy cannot group by a related model's field.
      // The submission table is bounded and reporting-sized (not a hot-path
      // per-request lookup — contrast the device_ai EcoID lookup, which
      // required an indexed column precisely because it *is* a hot path), so
      // a single projected findMany + in-memory reduce is the appropriate,
      // simplest correct implementation here.
      const rows = await prisma.submission.findMany({
        select: {
          estimatedWeight: true,
          recoveredWeight: true,
          status: true,
          assignedCollectorId: true,
          assignedRecyclerId: true,
          user: { select: { region: true } },
        },
      });

      interface Accumulator {
        totalSubmissions: number;
        totalWeight: number;
        recycledWeight: number;
        collectorIds: Set<string>;
        recyclerIds: Set<string>;
      }

      const byRegion = new Map<string, Accumulator>();

      for (const row of rows) {
        const region = row.user.region?.trim() || UNSPECIFIED_REGION;
        let acc = byRegion.get(region);
        if (!acc) {
          acc = {
            totalSubmissions: 0,
            totalWeight: 0,
            recycledWeight: 0,
            collectorIds: new Set(),
            recyclerIds: new Set(),
          };
          byRegion.set(region, acc);
        }

        acc.totalSubmissions += 1;
        acc.totalWeight += row.estimatedWeight;
        if (RECYCLED_STATUSES.includes(row.status) && row.recoveredWeight != null) {
          acc.recycledWeight += row.recoveredWeight;
        }
        if (row.assignedCollectorId) acc.collectorIds.add(row.assignedCollectorId);
        if (row.assignedRecyclerId) acc.recyclerIds.add(row.assignedRecyclerId);
      }

      return Array.from(byRegion.entries())
        .map(([region, acc]) => ({
          region,
          totalSubmissions: acc.totalSubmissions,
          totalWeight: acc.totalWeight,
          recycledWeight: acc.recycledWeight,
          activeCollectors: acc.collectorIds.size,
          activeRecyclers: acc.recyclerIds.size,
        }))
        .sort((a, b) => b.totalSubmissions - a.totalSubmissions);
    },

    async getDailyRecycledWeightSeries(): Promise<DailyWeightObservation[]> {
      // Definition: one real observation per submission whose recycling
      // actually completed — `recycledAt` is the only lifecycle timestamp
      // paired with a real *measured* weight (`recoveredWeight`); it is set
      // exactly once per submission by the recycler-completion workflow
      // (submission.repository.ts's updateRecyclerCompletion), so there is
      // no risk of double-counting a submission across dates. `estimatedWeight`
      // (set at creation) is a consumer's guess, not a measurement, and
      // `completedAt` is never written anywhere in this codebase — so
      // `recycledAt`/`recoveredWeight` is the only defensible (date, weight)
      // pair to forecast from.
      const rows = await prisma.submission.findMany({
        where: { recycledAt: { not: null }, recoveredWeight: { not: null } },
        select: { recycledAt: true, recoveredWeight: true },
      });

      return aggregateDailyRecycledWeight(
        rows.map((row) => ({
          recycledAt: row.recycledAt as Date,
          recoveredWeight: row.recoveredWeight as number,
        })),
      );
    },
  };
}
