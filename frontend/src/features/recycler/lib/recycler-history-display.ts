/**
 * Recycler history & recovery-analytics presentation helpers.
 *
 * Pure functions over the real `GET /recycler/submissions/history` response
 * (`RecyclerHistoryEntry[]`) — no data fetching, no fabricated figures. Every
 * aggregate here is a sum/average/count over values the backend already
 * computed and stored (reward.service.ts for co2Saved/energySaved/
 * landfillDiverted; the recycler's own completion form for materialRecovery)
 * — nothing is estimated, inferred, or benchmarked against an invented
 * target. Mirrors the client-side aggregation pattern already established by
 * `recycler-display.ts`'s `computeRecyclerSummary` for the active queue.
 */
import type { RecyclerHistoryEntry } from '@/types';
import { materialRecoveryEntries } from '@/features/recycler/lib/recycler-display';

/**
 * Recovery rate as a percentage (0–100+), or `null` when it cannot be
 * honestly computed — either the job has no recorded recovered weight, or
 * `estimatedWeight` is not a positive number (division would be meaningless
 * or undefined). Formula: recoveredWeight / estimatedWeight * 100.
 */
export function recoveryRatePercent(
  estimatedWeight: number,
  recoveredWeight: number | null,
): number | null {
  if (recoveredWeight === null) return null;
  if (!Number.isFinite(estimatedWeight) || estimatedWeight <= 0) return null;
  return (recoveredWeight / estimatedWeight) * 100;
}

/** Facility-wide totals across every job in the recycler's real history. */
export interface RecyclerHistorySummary {
  totalJobs: number;
  totalEstimatedWeight: number;
  totalRecoveredWeight: number;
  /** Average of each job's own recovery rate, or `null` when no job has a computable rate. */
  averageRecoveryRate: number | null;
  totalCo2Saved: number;
  totalEnergySaved: number;
  totalLandfillDiverted: number;
}

/**
 * Aggregate the recycler's real completed-job list into facility totals.
 * Sums only ever add real, already-populated values (a `null` field
 * contributes 0 to a sum, exactly as "not recorded" should — it is never
 * treated as a fabricated data point for the average).
 */
export function computeHistorySummary(jobs: readonly RecyclerHistoryEntry[]): RecyclerHistorySummary {
  const rates: number[] = [];
  const summary: RecyclerHistorySummary = {
    totalJobs: jobs.length,
    totalEstimatedWeight: 0,
    totalRecoveredWeight: 0,
    averageRecoveryRate: null,
    totalCo2Saved: 0,
    totalEnergySaved: 0,
    totalLandfillDiverted: 0,
  };

  for (const job of jobs) {
    summary.totalEstimatedWeight += job.estimatedWeight;
    summary.totalRecoveredWeight += job.recoveredWeight ?? 0;
    summary.totalCo2Saved += job.co2Saved ?? 0;
    summary.totalEnergySaved += job.energySaved ?? 0;
    summary.totalLandfillDiverted += job.landfillDiverted ?? 0;

    const rate = recoveryRatePercent(job.estimatedWeight, job.recoveredWeight);
    if (rate !== null) rates.push(rate);
  }

  if (rates.length > 0) {
    summary.averageRecoveryRate = rates.reduce((sum, rate) => sum + rate, 0) / rates.length;
  }

  return summary;
}

/** One material's aggregated recovered weight across every job that recorded it. */
export interface MaterialSummaryRow {
  name: string;
  totalWeight: number;
}

/** Real material-recovery aggregation, plus how many jobs actually recorded it. */
export interface MaterialSummary {
  materials: MaterialSummaryRow[];
  /** Jobs whose `materialRecovery` had at least one recorded entry. */
  jobsWithMaterialData: number;
  totalJobs: number;
}

/**
 * Aggregate real per-material recovered weights across the recycler's
 * history. Only ever sums entries the recycler actually recorded — a job
 * with no `materialRecovery` contributes nothing (never a guessed
 * breakdown), and `jobsWithMaterialData` is reported alongside so the UI can
 * honestly disclose how partial the data is (see `analytics-display.ts`'s
 * "not recorded" convention for the same honesty rule elsewhere).
 */
export function computeMaterialSummary(jobs: readonly RecyclerHistoryEntry[]): MaterialSummary {
  const totals = new Map<string, number>();
  let jobsWithMaterialData = 0;

  for (const job of jobs) {
    const entries = materialRecoveryEntries(job.materialRecovery);
    if (entries.length === 0) continue;
    jobsWithMaterialData += 1;
    for (const { name, weight } of entries) {
      totals.set(name, (totals.get(name) ?? 0) + weight);
    }
  }

  const materials = [...totals.entries()]
    .map(([name, totalWeight]) => ({ name, totalWeight }))
    .sort((a, b) => b.totalWeight - a.totalWeight);

  return { materials, jobsWithMaterialData, totalJobs: jobs.length };
}

/** One category's real aggregated counts/weights across the recycler's history. */
export interface CategoryBreakdownRow {
  category: string;
  count: number;
  totalEstimatedWeight: number;
  totalRecoveredWeight: number;
}

/**
 * Presentation-only normalization of a category string for grouping (trims
 * and title-cases, e.g. "LAPTOP"/"laptop"/"Laptop" all display as "Laptop").
 * This groups real duplicate-meaning labels for a legible table — it never
 * invents a category that wasn't recorded, and the counts/weights behind it
 * are the real, unmodified sums. Mirrors the same capitalization convention
 * `reward-display.ts`'s `rewardReasonLabel` already uses elsewhere.
 */
function normalizeCategoryLabel(category: string): string {
  const trimmed = category.trim();
  if (!trimmed) return trimmed;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1).toLowerCase();
}

/**
 * Group the recycler's real completed jobs by category. Whatever categories
 * genuinely exist in the data are exactly what appears here — including a
 * single category if that's all the recycler has ever processed.
 */
export function computeCategoryBreakdown(
  jobs: readonly RecyclerHistoryEntry[],
): CategoryBreakdownRow[] {
  const rows = new Map<string, CategoryBreakdownRow>();

  for (const job of jobs) {
    const label = normalizeCategoryLabel(job.category);
    const existing = rows.get(label);
    if (existing) {
      existing.count += 1;
      existing.totalEstimatedWeight += job.estimatedWeight;
      existing.totalRecoveredWeight += job.recoveredWeight ?? 0;
    } else {
      rows.set(label, {
        category: label,
        count: 1,
        totalEstimatedWeight: job.estimatedWeight,
        totalRecoveredWeight: job.recoveredWeight ?? 0,
      });
    }
  }

  return [...rows.values()].sort((a, b) => b.count - a.count);
}
